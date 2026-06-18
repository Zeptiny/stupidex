"""Tests for Sidebar Collapsible teardown safety.

Regression coverage for Bug A: the subagent sidebar rebuilds a
``Collapsible(classes='finished-collapse')`` for finished subagents and mounts
its entries by querying ``Contents`` *immediately after* mounting the
collapsible. During app teardown (exit while subagents are still running), the
1s subagent timer can fire into a partially-dismantled DOM and the
post-mount ``query_one("Contents")`` raises ``NoMatches``.

The fix mounts the finished entries as positional children of the
``Collapsible`` constructor so they are part of its ``compose()`` output,
removing the fragile post-mount query. This test asserts that contract: the
done entries are descendants of the Collapsible without a separate
``contents.mount`` step, and rebuilding during teardown does not raise.
"""
import unittest
from unittest.mock import patch

from textual.app import App, ComposeResult
from textual.widgets import Collapsible

from stupidex.agents.manager import SubagentRecord, SubagentState
from stupidex.widgets.sidebar import NavEntry, Sidebar


def _record(rid: str, state: SubagentState = SubagentState.COMPLETED, label: str = "agent") -> SubagentRecord:
    """Build a SubagentRecord without the Agent dependency the constructor requires."""
    r = object.__new__(SubagentRecord)
    r.id = rid
    r.agent = None  # type: ignore[assignment] — label short-circuits the `name` property
    r.state = state
    r.label = label
    r.task = ""
    r.async_task = None
    r.result = None
    r.error = None
    r.start_time = 0.0
    r.end_time = None
    r.messages = []
    r.messages_mounted = 0
    r.on_message = None
    r.on_state_change = None
    return r


class _SidebarApp(App):
    def compose(self) -> ComposeResult:
        yield Sidebar(id="sidebar")


class TestSidebarCollapsibleTeardown(unittest.IsolatedAsyncioTestCase):
    async def test_finished_entries_become_collapsible_children(self):
        """Done NavEntries must be descendants of the Collapsible after
        ``update_subagents``, populated via the Collapsible's own compose
        rather than a fragile post-mount ``query_one('Contents')``."""
        async with _SidebarApp().run_test() as pilot:
            sidebar = pilot.app.query_one("#sidebar", Sidebar)
            records: list[SubagentRecord] = [
                _record("s1", SubagentState.COMPLETED, "first"),
                _record("s2", SubagentState.COMPLETED, "second"),
            ]
            await sidebar.update_subagents(records)
            await pilot.pause()

            collapsibles = sidebar.query(Collapsible)
            self.assertEqual(len(collapsibles), 1)
            collapse = collapsibles[0]
            self.assertIn("finished-collapse", collapse.classes)

            # The done entries should be present inside the collapsible's
            # Contents, without relying on a separate mount step.
            entries = collapse.query(NavEntry)
            entry_ids = {e.view_id for e in entries}
            self.assertEqual(entry_ids, {"s1", "s2"})

    async def test_update_subagents_tolerates_unqueryable_contents(self):
        """During app teardown, the freshly-mounted Collapsible's ``Contents``
        node may not be queryable (partial compose), which previously raised
        ``NoMatches``. The rebuild must not depend on a post-mount
        ``query_one('Contents')``: the done entries are passed as Collapsible
        children so they are part of its own ``compose()``.

        This simulates the teardown condition by making
        ``Collapsible.query_one('Contents')`` raise ``NoMatches``; the buggy
        code (which calls that query) raises, the fixed code does not.
        """
        from textual.css.query import NoMatches

        async with _SidebarApp().run_test() as pilot:
            sidebar = pilot.app.query_one("#sidebar", Sidebar)
            await sidebar.update_subagents([_record("s1")])
            await pilot.pause()

            real_query_one = Collapsible.query_one

            def query_one_raising_contents(self, selector=None, *args, **kwargs):  # type: ignore[no-untyped-def]
                # Simulate the teardown state where Contents is not yet
                # queryable right after mount.
                sel = selector if isinstance(selector, str) else ""
                if "Contents" in sel:
                    raise NoMatches("No nodes match 'Contents' (simulated teardown)")
                return real_query_one(self, selector, *args, **kwargs)

            with patch.object(Collapsible, "query_one", query_one_raising_contents):
                try:
                    await sidebar.update_subagents([
                        _record("s2", SubagentState.COMPLETED, "second"),
                    ])
                except NoMatches as exc:
                    self.fail(
                        "update_subagents raised NoMatches by depending on "
                        f"query_one('Contents'): {exc!r}"
                    )
                await pilot.pause()

            # Entries were still attached via the Collapsible's compose.
            collapse = sidebar.query_one(Collapsible)
            entry_ids = {e.view_id for e in collapse.query(NavEntry)}
            self.assertEqual(entry_ids, {"s2"})
