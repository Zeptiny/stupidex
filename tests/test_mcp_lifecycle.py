"""Tests for MCPManager lifecycle safety.

Regression coverage for Bug B: ``stdio_client`` (and ``sse_client``) wrap an
``anyio`` task group / cancel scope. Entering the context in one task and
exiting it from another raises::

    RuntimeError: Attempted to exit cancel scope in a different task than it
    was entered in.

In the app, ``MCPManager.start_all`` runs from ``App.on_mount`` while
``MCPManager.shutdown`` runs from ``App.on_exit`` — these are dispatched by
Textual in *different* tasks. The manager must therefore guarantee that the
enter/exit pair for every transport happens in a single owning task. When the
guarantee is violated, ``shutdown`` swallows the ``RuntimeError`` (logging a
warning) and the transport's subprocess / reader subtasks leak.
"""
import asyncio
import logging
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

import anyio


@asynccontextmanager
async def fake_stdio_client(*args, **kwargs):
    """Mimics ``mcp.client.stdio.stdio_client``'s anyio task-group behaviour.

    The real transport opens an ``anyio.create_task_group()`` and starts
    long-lived reader/writer subtasks inside it; its cancel scope is
    task-bound. Exiting that scope from a different task than the one that
    entered it raises ``RuntimeError`` — exactly the production failure. A bare
    task group with no subtasks exits trivially and would not reproduce the
    cross-task check, so a long-lived subtask is spawned to match the real
    transport's shape.
    """

    async def reader():
        try:
            await anyio.sleep_forever()
        except anyio.get_cancelled_exc_class():
            pass

    async with anyio.create_task_group() as tg:
        tg.start_soon(reader)
        try:
            yield (object(), object())
        finally:
            tg.cancel_scope.cancel()


class _ToolsResult:
    def __init__(self):
        self.tools = []


class _ResourcesResult:
    def __init__(self):
        self.resources = []


class FakeClientSession:
    """Stand-in for ``mcp.ClientSession`` that owns no real transport."""

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def initialize(self):
        return None

    async def list_tools(self):
        return _ToolsResult()

    async def list_resources(self):
        return _ResourcesResult()


class _RecordingHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class TestMCPLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_from_different_task_does_not_raise(self):
        """``shutdown`` must be callable from a different task than ``start_all``.

        When the transport contexts are entered during ``start_all`` (task A)
        and closed during ``shutdown`` (task B), anyio's task-bound cancel
        scope must not raise ``Attempted to exit cancel scope in a different
        task``. The buggy implementation swallows that error inside
        ``shutdown``'s ``except`` (logging a warning), so we assert the warning
        is absent — both the raised error and its swallowed form are failures.
        """
        from stupidex.mcp import MCPManager

        manager = MCPManager()
        servers = {
            "srv1": {"command": "fake", "args": []},
            "srv2": {"command": "fake", "args": []},
        }

        handler = _RecordingHandler()
        logger = logging.getLogger("stupidex.mcp")
        logger.addHandler(handler)
        shutdown_error: BaseException | None = None
        try:
            with (
                patch("stupidex.mcp.stdio_client", fake_stdio_client),
                patch("stupidex.mcp.ClientSession", FakeClientSession),
            ):
                await manager.start_all(servers)

                async def shutdown_in_other_task():
                    nonlocal shutdown_error
                    try:
                        await manager.shutdown()
                    except BaseException as exc:  # noqa: BLE001 - assert no error escapes
                        shutdown_error = exc

                await asyncio.create_task(shutdown_in_other_task())
        finally:
            logger.removeHandler(handler)

        self.assertIsNone(
            shutdown_error,
            f"shutdown propagated: {shutdown_error!r}",
        )
        shutdown_warnings = [
            r
            for r in handler.records
            if r.levelno >= logging.WARNING and "shutdown" in (r.getMessage() or "").lower()
        ]
        self.assertEqual(
            shutdown_warnings,
            [],
            "shutdown logged a warning (swallowed cross-task "
            f"error): {[r.getMessage() for r in shutdown_warnings]}",
        )

    async def test_start_all_reinitializes_lifecycle_for_restart(self):
        """A manager can be ``start_all``-ed again after ``shutdown``.

        The one-shot ``asyncio.Event``s and the closed ``AsyncExitStack`` must
        be reinitialized at the start of ``start_all``; otherwise the second
        run returns before the runner enters any transport (``_ready`` already
        set) and its ``finally`` closes the stack immediately (``_stop``
        already set).
        """
        from stupidex.mcp import MCPManager

        manager = MCPManager()
        servers = {"srv1": {"command": "fake", "args": []}}

        with (
            patch("stupidex.mcp.stdio_client", fake_stdio_client),
            patch("stupidex.mcp.ClientSession", FakeClientSession),
        ):
            await manager.start_all(servers)
            self.assertEqual(
                manager.get_server_statuses()["srv1"]["status"],
                "connected",
            )
            await manager.shutdown()

            # Second lifecycle on the same instance must work end to end.
            await manager.start_all(servers)
            self.assertEqual(
                manager.get_server_statuses()["srv1"]["status"],
                "connected",
            )
            await manager.shutdown()

    async def test_start_all_rejects_concurrent_start(self):
        """A second ``start_all`` while a runner is active must raise, rather
        than overwrite ``_runner`` and corrupt the in-flight run's state."""
        from stupidex.mcp import MCPManager

        manager = MCPManager()
        servers = {"srv1": {"command": "fake", "args": []}}

        with (
            patch("stupidex.mcp.stdio_client", fake_stdio_client),
            patch("stupidex.mcp.ClientSession", FakeClientSession),
        ):
            await manager.start_all(servers)
            try:
                with self.assertRaises(RuntimeError):
                    await manager.start_all(servers)
            finally:
                await manager.shutdown()
