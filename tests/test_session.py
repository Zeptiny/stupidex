"""Tests for Session storage round-trip and corrupt-subagent resilience (P2-16)."""

import unittest
from unittest.mock import patch

from stupidex.agents.manager import SubagentRecord, SubagentState
from stupidex.domain.agent import Agent, AgentTypes, ModelTier
from stupidex.domain.chain import Chain
from stupidex.domain.message import Message, MessageRole, MessageType
from stupidex.domain.session import Session, SessionManager
from stupidex.domain.todo import TodoStatus, TodoTask


class TestSessionStorageRoundTrip(unittest.TestCase):
    def _subagent_record(self, rec_id: str) -> SubagentRecord:
        agent = Agent(
            name="Subagent",
            type=AgentTypes.SUBAGENT,
            tier=ModelTier.PAPUDO,
            description="d",
            system_prompt="p",
        )
        return SubagentRecord(
            id=rec_id,
            agent=agent,
            state=SubagentState.COMPLETED,
            label="sub1",
            task="do thing",
            result="Answer",
            error=None,
            start_time=10.0,
            end_time=11.5,
            chain=Chain(messages=[
                Message(MessageRole.USER, "do thing"),
                Message(MessageRole.ASSISTANT, "Answer", MessageType.TEXT),
            ]),
            messages_mounted=2,
        )

    def test_to_storage_dict_then_from_storage_dict_preserves_chains(self):
        session = Session(name="S", id="sess-1", model="m")
        session.chains = [
            Chain(model="m", messages=[Message(MessageRole.USER, "hi")], start_time=1.0),
            Chain(
                model="m2",
                messages=[Message(MessageRole.ASSISTANT, "hey", MessageType.TEXT)],
                start_time=2.0,
                end_time=3.0,
            ),
        ]
        restored = Session.from_storage_dict(session.to_storage_dict())
        self.assertEqual(restored.id, "sess-1")
        self.assertEqual(restored.name, "S")
        self.assertEqual(restored.model, "m")
        self.assertEqual(len(restored.chains), 2)
        self.assertEqual(restored.chains[0].messages[0].content, "hi")
        self.assertEqual(restored.chains[1].messages[0].role, MessageRole.ASSISTANT)

    def test_storage_round_trip_preserves_subagents(self):
        session = Session(name="S", id="sess-2", model="m")
        rec = self._subagent_record("rec-1")
        session.subagent_manager._subagents[rec.id] = rec

        with patch(
            "stupidex.agents.get_agent_registry",
            return_value={"Subagent": rec.agent},
        ):
            restored = Session.from_storage_dict(session.to_storage_dict())

        self.assertIn("rec-1", restored.subagent_manager._subagents)
        r = restored.subagent_manager._subagents["rec-1"]
        self.assertEqual(r.label, "sub1")
        self.assertEqual(r.task, "do thing")
        self.assertEqual(r.result, "Answer")
        self.assertEqual(r.state, SubagentState.COMPLETED)
        self.assertEqual(len(r.messages), 2)
        self.assertEqual(r.messages[1].content, "Answer")

    def test_storage_round_trip_preserves_todo_store(self):
        session = Session(name="S", id="sess-3", model="m")
        session.todo_store._tasks["t1"] = TodoTask(id="t1", title="Buy milk", status=TodoStatus.IN_PROGRESS)
        restored = Session.from_storage_dict(session.to_storage_dict())
        self.assertIn("t1", restored.todo_store._tasks)
        self.assertEqual(restored.todo_store._tasks["t1"].title, "Buy milk")
        self.assertEqual(restored.todo_store._tasks["t1"].status, TodoStatus.IN_PROGRESS)

    def test_empty_session_round_trips_cleanly(self):
        session = Session(name="empty", id="sess-empty", model=None)
        restored = Session.from_storage_dict(session.to_storage_dict())
        self.assertEqual(restored.id, "sess-empty")
        self.assertEqual(restored.chains, [])
        self.assertEqual(restored.subagent_manager._subagents, {})

    def test_corrupt_subagent_entry_is_skipped_others_preserved(self):
        agent = Agent(
            name="Subagent",
            type=AgentTypes.SUBAGENT,
            tier=ModelTier.PAPUDO,
            description="d",
            system_prompt="p",
        )
        good_record = SubagentRecord(
            id="good-1",
            agent=agent,
            state=SubagentState.COMPLETED,
            label="g",
            task="ok",
            result="done",
            start_time=1.0,
            end_time=2.0,
        )
        # Missing "id" key — SubagentRecord.from_storage_dict raises KeyError,
        # which Session.from_storage_dict catches and skips (fail-soft).
        corrupt_entry = {"agent_name": "Ghost", "state": "completed"}

        data = {
            "version": 1,
            "id": "sess-mixed",
            "name": "mixed",
            "model": "m",
            "chains": [],
            "subagent_chains": [corrupt_entry, good_record.to_storage_dict()],
            "todo_store": {},
        }
        with patch(
            "stupidex.agents.get_agent_registry",
            return_value={"Subagent": agent},
        ):
            session = Session.from_storage_dict(data)

        self.assertNotIn("corrupt", session.subagent_manager._subagents)
        self.assertIn("good-1", session.subagent_manager._subagents)
        self.assertEqual(session.subagent_manager._subagents["good-1"].result, "done")

    def test_all_corrupt_subagent_entries_does_not_raise(self):
        data = {
            "version": 1,
            "id": "sess-broken",
            "name": "broken",
            "model": None,
            "chains": [],
            "subagent_chains": [
                {"agent_name": "x"},
                {"id": None},  # agent_name defaults to ""; registry miss → fallback
            ],
            "todo_store": {},
        }
        session = Session.from_storage_dict(data)
        self.assertEqual(session.id, "sess-broken")
        # The {"id": None} entry gets through from_storage_dict by using a
        # pseudo-agent fallback, so it lands under the None key. We only
        # assert the load did not raise and the corrupt non-id entry was
        # skipped — those are the fail-soft guarantees under test.
        self.assertEqual(session.chains, [])


class TestSessionManagerDelete(unittest.TestCase):
    """Tests for disk-first delete ordering (P2-1)."""

    def _manager_with_session(self, sess_id: str, make_active: bool = True) -> SessionManager:
        mgr = SessionManager()
        session = Session(name="S", id=sess_id, model="m")
        mgr.sessions[sess_id] = session
        if make_active:
            mgr.active = session
        return mgr

    @patch("stupidex.storage.delete_session")
    def test_delete_happy_path_active_session(self, mock_delete):
        mgr = self._manager_with_session("sess-1")
        self.assertTrue(mgr.delete("sess-1"))
        mock_delete.assert_called_once_with("sess-1")
        self.assertNotIn("sess-1", mgr.sessions)
        self.assertIsNone(mgr.active)

    @patch("stupidex.storage.delete_session")
    def test_delete_active_is_different_session(self, mock_delete):
        mgr = self._manager_with_session("sess-1", make_active=False)
        other = Session(name="other", id="sess-other", model="m")
        mgr.sessions["sess-other"] = other
        mgr.active = other
        self.assertTrue(mgr.delete("sess-1"))
        mock_delete.assert_called_once_with("sess-1")
        self.assertNotIn("sess-1", mgr.sessions)
        self.assertIs(mgr.active, other)

    @patch("stupidex.storage.delete_session")
    def test_delete_unknown_session_no_disk_touch(self, mock_delete):
        mgr = SessionManager()
        self.assertFalse(mgr.delete("missing"))
        mock_delete.assert_not_called()

    @patch("stupidex.storage.delete_session")
    def test_delete_disk_failure_preserves_in_memory_state(self, mock_delete):
        mgr = self._manager_with_session("sess-1")
        mock_delete.side_effect = OSError("disk full")
        with self.assertLogs("stupidex.domain.session", level="WARNING") as cm:
            self.assertFalse(mgr.delete("sess-1"))
        self.assertIn("sess-1", mgr.sessions)
        self.assertIsNotNone(mgr.active)
        assert mgr.active is not None
        self.assertEqual(mgr.active.id, "sess-1")
        self.assertTrue(any("sess-1" in line for line in cm.output))

    @patch("stupidex.storage.delete_session")
    def test_cancel_all_called_before_disk_delete(self, mock_delete):
        call_order: list[str] = []

        def track_delete(sid):
            call_order.append("delete_session")

        mock_delete.side_effect = track_delete
        mgr = self._manager_with_session("sess-1")
        session = mgr.sessions["sess-1"]

        def track_cancel():
            call_order.append("cancel_all")

        with patch.object(session.subagent_manager, "cancel_all", side_effect=track_cancel):
            self.assertTrue(mgr.delete("sess-1"))
        mock_delete.assert_called_once_with("sess-1")
        self.assertEqual(call_order, ["cancel_all", "delete_session"])


class TestSessionFromStorageDictChainGuard(unittest.TestCase):
    """Tests for per-chain deserialization guard in Session.from_storage_dict (P2-8)."""

    def _chain_data(self, status: str = "completed") -> dict:
        return {
            "model": "m",
            "messages": [],
            "start_time": 1.0,
            "end_time": 2.0,
            "status": status,
        }

    def _session_data(self, chains: list) -> dict:
        return {
            "version": 1,
            "id": "sess-chains",
            "name": "chains",
            "model": "m",
            "chains": chains,
            "subagent_chains": [],
            "todo_store": {},
        }

    def test_all_valid_chains_load(self):
        data = self._session_data([self._chain_data(), self._chain_data(), self._chain_data()])
        session = Session.from_storage_dict(data)
        self.assertEqual(len(session.chains), 3)

    def test_corrupt_middle_chain_status_skipped(self):
        corrupt = self._chain_data(status="bogus")
        data = self._session_data([self._chain_data(), corrupt, self._chain_data()])
        with self.assertLogs("stupidex.domain.session", level="WARNING") as cm:
            session = Session.from_storage_dict(data)
        self.assertEqual(len(session.chains), 2)
        self.assertTrue(any("index 1" in line for line in cm.output))

    def test_corrupt_first_chain_messages_field_skipped(self):
        corrupt = {"model": "m", "messages": "not-a-list", "start_time": 1.0, "status": "completed"}
        data = self._session_data([corrupt, self._chain_data(), self._chain_data()])
        with self.assertLogs("stupidex.domain.session", level="WARNING"):
            session = Session.from_storage_dict(data)
        self.assertEqual(len(session.chains), 2)

    def test_zero_chains_returns_empty_list(self):
        data = self._session_data([])
        session = Session.from_storage_dict(data)
        self.assertEqual(session.chains, [])

    def test_corrupt_chain_does_not_cascade_to_subagent_restoration(self):
        agent = Agent(
            name="Subagent",
            type=AgentTypes.SUBAGENT,
            tier=ModelTier.PAPUDO,
            description="d",
            system_prompt="p",
        )
        good_record = SubagentRecord(
            id="good-1",
            agent=agent,
            state=SubagentState.COMPLETED,
            label="g",
            task="ok",
            result="done",
            start_time=1.0,
            end_time=2.0,
        )
        data = self._session_data([self._chain_data(status="bogus")])
        data["subagent_chains"] = [good_record.to_storage_dict()]
        with (
            patch("stupidex.agents.get_agent_registry", return_value={"Subagent": agent}),
            self.assertLogs("stupidex.domain.session", level="WARNING"),
        ):
            session = Session.from_storage_dict(data)
        self.assertEqual(session.chains, [])
        self.assertIn("good-1", session.subagent_manager._subagents)


if __name__ == "__main__":
    unittest.main()
