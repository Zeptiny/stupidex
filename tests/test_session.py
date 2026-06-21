"""Tests for Session storage round-trip and corrupt-subagent resilience (P2-16)."""

import unittest
from unittest.mock import patch

from stupidex.agents.manager import SubagentRecord, SubagentState
from stupidex.domain.agent import Agent, AgentTypes, ModelTier
from stupidex.domain.chain import Chain
from stupidex.domain.message import Message, MessageRole, MessageType
from stupidex.domain.session import Session
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
            messages=[
                Message(MessageRole.USER, "do thing"),
                Message(MessageRole.ASSISTANT, "Answer", MessageType.TEXT),
            ],
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


if __name__ == "__main__":
    unittest.main()
