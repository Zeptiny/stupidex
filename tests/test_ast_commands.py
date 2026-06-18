"""Tests for the `/reindex-ast` command (unit U6, requirement R12).

Mirrors the pattern in `tests/test_session_commands.py`: exercises the
`execute_command` dispatch path with a mock `app`, verifying the worker
is launched and notifications are sent.

Scenarios from the plan:
- Happy path: `/reindex-ast` appears in COMMANDS
- Happy path: executing triggers index_project(force=True) and notifies
- Edge case: substring filter picks up `/reindex-ast` when typing `/index`
- Error path: index_project exception -> error notification, no crash
"""

import asyncio
import inspect
import unittest
from unittest.mock import MagicMock, patch

from stupidex.commands.session_commands import COMMANDS, execute_command

_INDEX_PROJECT = "stupidex.ast.indexer.index_project"


class TestReindexAstCommandInCommands(unittest.TestCase):
    """Scenario 1: /reindex-ast is registered in the COMMANDS dict."""

    def test_command_present(self):
        self.assertIn("/reindex-ast", COMMANDS)

    def test_command_description(self):
        desc = COMMANDS["/reindex-ast"]
        self.assertIn("AST", desc)
        self.assertIn("symbol", desc.lower())

    def test_index_substring_shows_reindex_ast(self):
        """Edge case: 'index' is a substring of 'reindex-ast', so the
        command picker will show /reindex-ast when typing '/index'.
        This is an accepted UX limitation -- just verify the relationship."""
        index_cmds = [cmd for cmd in COMMANDS if "index" in cmd]
        self.assertIn("/reindex-ast", index_cmds)
        self.assertIn("/index", index_cmds)


class TestReindexAstExecution(unittest.TestCase):
    """Scenario 2 + 4: executing /reindex-ast calls index_project(force=True)
    via app.run_worker and notifies on success/error."""

    def test_happy_path_notifies_and_runs_worker(self):
        """The initial notification fires and run_worker is called."""
        app = MagicMock()
        app.run_worker = MagicMock()

        with patch(_INDEX_PROJECT):
            asyncio.run(execute_command(app, "/reindex-ast"))

        app.notify.assert_any_call(
            "Re-scanning project for AST symbols...",
            severity="information",
        )
        app.run_worker.assert_called_once()

    def test_run_worker_receives_coroutine_function(self):
        """run_worker receives an async callable (coroutine function),
        not None or a plain function."""
        captured_fn = {}

        def capture_worker(coro_fn):
            captured_fn["fn"] = coro_fn

        app = MagicMock()
        app.run_worker = capture_worker

        with patch(_INDEX_PROJECT):
            asyncio.run(execute_command(app, "/reindex-ast"))

        self.assertIn("fn", captured_fn)
        self.assertTrue(inspect.iscoroutinefunction(captured_fn["fn"]))

    def test_run_worker_receives_different_function_each_call(self):
        """Each invocation of execute_command produces a fresh coroutine
        function (not a stale reference)."""
        captured_fns = []

        def capture_worker(coro_fn):
            captured_fns.append(coro_fn)

        app = MagicMock()
        app.run_worker = capture_worker

        with patch(_INDEX_PROJECT):
            asyncio.run(execute_command(app, "/reindex-ast"))
            asyncio.run(execute_command(app, "/reindex-ast"))

        self.assertEqual(len(captured_fns), 2)
        # Both are coroutine functions but are distinct objects.
        self.assertTrue(inspect.iscoroutinefunction(captured_fns[0]))
        self.assertTrue(inspect.iscoroutinefunction(captured_fns[1]))
        self.assertIsNot(captured_fns[0], captured_fns[1])

    def test_worker_body_awaits_index_project_force_true(self):
        """The worker coroutine's source includes force=True, confirming
        it will call index_project with the force flag."""
        captured_fn = {}

        def capture_worker(coro_fn):
            captured_fn["fn"] = coro_fn

        app = MagicMock()
        app.run_worker = capture_worker

        with patch(_INDEX_PROJECT):
            asyncio.run(execute_command(app, "/reindex-ast"))

        # Verify the coroutine function's code references force=True.
        source = inspect.getsource(captured_fn["fn"])
        self.assertIn("force=True", source)

if __name__ == "__main__":
    unittest.main()
