"""Tests for SubagentUIManager mount-lock serialization and eviction."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from stupidex.agents.manager import SubagentState
from stupidex.domain.message import Message, MessageRole, MessageType
from stupidex.widgets.subagent_ui import SubagentUIManager


class _ConcurrencyTracker:
    """Stub for ``mount_streamed_message`` that records concurrency.

    Each call blocks on ``gate`` until the test sets it, letting us observe
    how many calls are inside the stub (i.e. past the mount lock) at once.
    """

    def __init__(self) -> None:
        self.active: int = 0
        self.max_concurrent: int = 0
        self.gate: asyncio.Event = asyncio.Event()
        self.entered: asyncio.Event = asyncio.Event()

    async def __call__(self, container, msg, state) -> None:
        self.active += 1
        self.max_concurrent = max(self.max_concurrent, self.active)
        self.entered.set()
        try:
            await self.gate.wait()
        finally:
            self.active -= 1


def _make_manager_for_messages() -> tuple[SubagentUIManager, MagicMock]:
    """Build a manager whose ``app.query_one`` returns a pane with a container.

    Suitable for driving ``on_message``: the pane's ``query_one`` yields a
    container mock, so the scroll-container lookup in ``on_message`` succeeds
    without touching the real Textual widget tree.
    """
    app = MagicMock()
    container = MagicMock()
    pane = MagicMock()
    pane.query_one.return_value = container
    app.query_one.return_value = pane
    mgr = SubagentUIManager(app)
    return mgr, pane


def _text_message() -> Message:
    return Message(role=MessageRole.ASSISTANT, content="hi", type=MessageType.TEXT)


class TestMountLockConcurrency(unittest.IsolatedAsyncioTestCase):
    async def test_concurrent_mounts_same_subagent_serialized(self) -> None:
        """Two concurrent on_message calls for the same subagent_id are
        serialized by the per-subagent mount lock: at most one is ever
        inside mount_streamed_message at a time."""
        mgr, _ = _make_manager_for_messages()
        tracker = _ConcurrencyTracker()
        msg = _text_message()

        with patch("stupidex.widgets.subagent_ui.mount_streamed_message", tracker):
            t1 = asyncio.create_task(mgr.on_message("sa1", msg))
            await tracker.entered.wait()

            t2 = asyncio.create_task(mgr.on_message("sa1", msg))
            # Give t2 a chance to either enter the stub (bug) or block on lock.
            for _ in range(50):
                await asyncio.sleep(0.01)
                if tracker.active == 2:
                    break

            self.assertEqual(tracker.max_concurrent, 1)
            self.assertEqual(tracker.active, 1)

            tracker.gate.set()
            await asyncio.gather(t1, t2)

        self.assertEqual(tracker.max_concurrent, 1)

    async def test_concurrent_mounts_different_subagents_parallel(self) -> None:
        """Two on_message calls for distinct subagent_ids run in parallel:
        both enter mount_streamed_message concurrently (max_concurrent == 2)."""
        mgr, _ = _make_manager_for_messages()
        tracker = _ConcurrencyTracker()
        msg = _text_message()

        with patch("stupidex.widgets.subagent_ui.mount_streamed_message", tracker):
            t1 = asyncio.create_task(mgr.on_message("sa1", msg))
            await tracker.entered.wait()

            t2 = asyncio.create_task(mgr.on_message("sa2", msg))
            for _ in range(50):
                await asyncio.sleep(0.01)
                if tracker.active == 2:
                    break

            self.assertEqual(tracker.max_concurrent, 2)
            self.assertEqual(tracker.active, 2)

            tracker.gate.set()
            await asyncio.gather(t1, t2)

        self.assertEqual(tracker.max_concurrent, 2)


class TestLockEviction(unittest.IsolatedAsyncioTestCase):
    def _make_manager_for_state_change(self) -> tuple[SubagentUIManager, MagicMock, MagicMock]:
        """Build a manager whose app.query_one('#tabs', ...) returns a tabs
        mock whose get_tab(...) succeeds, and whose sessions.active exposes a
        subagent_manager with a get_record that returns a record."""
        app = MagicMock()
        tabs = MagicMock()
        tab = MagicMock()
        tabs.get_tab.return_value = tab
        manager = MagicMock()
        record = MagicMock()
        manager.get_record.return_value = record
        sessions = MagicMock()
        sessions.active.subagent_manager = manager
        app.sessions = sessions

        def query_one(selector, cls=None):
            return tabs

        app.query_one.side_effect = query_one
        mgr = SubagentUIManager(app)
        return mgr, manager, record

    async def test_lock_evicted_on_terminal_state(self) -> None:
        """Reaching INTERRUPTED (a terminal state) prunes the mount lock for
        that subagent_id."""
        mgr, _manager, _record = self._make_manager_for_state_change()
        mgr._mount_locks["sa1"] = asyncio.Lock()
        self.assertIn("sa1", mgr._mount_locks)

        with patch.object(mgr, "update_sidebar", new_callable=AsyncMock):
            await mgr.on_state_change("sa1", SubagentState.INTERRUPTED)

        self.assertNotIn("sa1", mgr._mount_locks)

    async def test_lock_not_evicted_on_nonterminal_state(self) -> None:
        """Non-terminal states (RUNNING) must not evict the lock."""
        mgr, _manager, _record = self._make_manager_for_state_change()
        lock = asyncio.Lock()
        mgr._mount_locks["sa1"] = lock

        with patch.object(mgr, "update_sidebar", new_callable=AsyncMock):
            await mgr.on_state_change("sa1", SubagentState.RUNNING)

        self.assertIs(mgr._mount_locks["sa1"], lock)

    async def test_lock_recreated_after_eviction(self) -> None:
        """After eviction, a new on_message creates a fresh lock via
        setdefault (a new asyncio.Lock instance, not the evicted one)."""
        mgr, _pane = _make_manager_for_messages()
        old_lock = asyncio.Lock()
        mgr._mount_locks["sa1"] = old_lock

        mgr.prune_lock("sa1")
        self.assertNotIn("sa1", mgr._mount_locks)

        tracker = _ConcurrencyTracker()
        tracker.gate.set()
        msg = _text_message()

        with patch("stupidex.widgets.subagent_ui.mount_streamed_message", tracker):
            await mgr.on_message("sa1", msg)

        self.assertIn("sa1", mgr._mount_locks)
        self.assertIsNot(mgr._mount_locks["sa1"], old_lock)

    async def test_prune_lock_idempotent(self) -> None:
        """prune_lock on a missing subagent_id is a no-op."""
        mgr, _ = _make_manager_for_messages()
        mgr.prune_lock("never-existed")  # should not raise
        self.assertNotIn("never-existed", mgr._mount_locks)

    async def test_terminal_states_each_evict(self) -> None:
        """COMPLETED and FAILED also evict the lock, not just INTERRUPTED."""
        for state in (SubagentState.COMPLETED, SubagentState.FAILED, SubagentState.INTERRUPTED):
            with self.subTest(state=state):
                mgr, _manager, _record = self._make_manager_for_state_change()
                mgr._mount_locks["sa1"] = asyncio.Lock()
                with patch.object(mgr, "update_sidebar", new_callable=AsyncMock):
                    await mgr.on_state_change("sa1", state)
                self.assertNotIn("sa1", mgr._mount_locks)


if __name__ == "__main__":
    unittest.main()
