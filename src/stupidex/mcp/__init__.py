from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Coroutine
from contextvars import ContextVar
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.types import BlobResourceContents, TextResourceContents

from stupidex.domain.tool import ExecutorResult

logger = logging.getLogger(__name__)

_mcp_manager: ContextVar[MCPManager | None] = ContextVar('mcp_manager', default=None)


def get_mcp_manager() -> MCPManager | None:
    return _mcp_manager.get()


def set_mcp_manager(manager: MCPManager | None) -> None:
    _mcp_manager.set(manager)


class MCPManager:
    """Manages MCP client sessions and their transports.

    Each server runs in its own long-lived task that owns its
    :class:`AsyncExitStack`, so the ``anyio`` cancel scope is entered and
    exited in the same task.  All server tasks start in parallel so slow
    servers do not block fast ones.
    """

    def __init__(self):
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, dict] = {}
        self._uri_map: dict[str, str] = {}  # uri -> server_name
        self._server_status: dict[str, dict] = {}  # name -> {status, tool_count, error}
        self._runner: asyncio.Task | None = None
        self._server_tasks: list[asyncio.Task] = []
        self._ready: asyncio.Event = asyncio.Event()
        self._stop: asyncio.Event = asyncio.Event()
        self._start_error: BaseException | None = None
        self._on_status_change: Callable[[], Coroutine[Any, Any, None]] | None = None

    async def start_all(
        self,
        servers: dict[str, dict],
        on_status_change: Callable[[], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        if self._runner is not None and not self._runner.done():
            raise RuntimeError("MCPManager.start_all already in progress")
        # Reinitialize the one-shot lifecycle state so a manager can be
        # restarted after shutdown.
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._start_error = None
        self._server_tasks = []
        self._on_status_change = on_status_change
        for server_name in servers:
            self._server_status[server_name] = {"status": "starting", "tool_count": 0, "error": None}
        self._runner = asyncio.create_task(self._run(servers))
        await self._ready.wait()
        if self._start_error is not None:
            await self._await_runner()
            raise self._start_error

    async def _run(self, servers: dict[str, dict]) -> None:
        remaining = len(servers)
        done_starting = asyncio.Event()

        async def _on_started() -> None:
            nonlocal remaining
            remaining -= 1
            if remaining <= 0:
                done_starting.set()

        try:
            self._server_tasks = [
                asyncio.create_task(self._manage_server(name, config, _on_started))
                for name, config in servers.items()
            ]
            # Race startup completion against shutdown so we never deadlock
            # when shutdown() is called while servers are still starting.
            startup_wait = asyncio.create_task(done_starting.wait())
            stop_wait = asyncio.create_task(self._stop.wait())
            done, pending = await asyncio.wait(
                {startup_wait, stop_wait}, return_when=asyncio.FIRST_COMPLETED,
            )
            for p in pending:
                p.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await p
        except BaseException as e:
            self._start_error = e
        finally:
            self._ready.set()
            if not self._stop.is_set():
                await self._stop.wait()
            for t in self._server_tasks:
                t.cancel()
            for t in self._server_tasks:
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass

    async def _manage_server(self, name: str, config: dict, on_started: Callable[[], Coroutine[Any, Any, None]]) -> None:
        """Own the full lifecycle of one server: start, mark status, hold open, close."""
        stack = contextlib.AsyncExitStack()
        try:
            await stack.__aenter__()
            await self._start_server(name, config, stack)
            tool_count = sum(1 for k in self._tools if k.startswith(f"mcp_{name}_"))
            self._server_status[name] = {"status": "connected", "tool_count": tool_count, "error": None}
        except Exception as e:
            self._server_status[name] = {"status": "failed", "tool_count": 0, "error": str(e)[:80]}
            logger.warning("Failed to start MCP server '%s'", name, exc_info=True)
        finally:
            try:
                await on_started()
            except Exception:
                pass
            if self._on_status_change is not None:
                try:
                    await self._on_status_change()
                except Exception:
                    pass
        # Keep the stack open until shutdown signals stop or task is cancelled.
        try:
            await self._stop.wait()
        except asyncio.CancelledError:
            pass
        try:
            await stack.aclose()
        except Exception:
            logger.warning("Error closing MCP server '%s'", name, exc_info=True)

    async def _await_runner(self) -> None:
        self._stop.set()
        runner = self._runner
        if runner is not None:
            try:
                await runner
            except Exception:
                logger.warning("MCP runner task ended with an error", exc_info=True)
        self._runner = None

    async def _start_server(self, server_name: str, config: dict, stack: contextlib.AsyncExitStack) -> None:
        from stupidex.mcp.schema import convert_mcp_tool, make_mcp_executor

        if "url" in config:
            read_stream, write_stream = await stack.enter_async_context(sse_client(url=config["url"]))
        else:
            server_params = StdioServerParameters(
                command=config["command"],
                args=config.get("args", []),
                env=config.get("env"),
            )
            read_stream, write_stream = await stack.enter_async_context(stdio_client(server_params))

        session: ClientSession = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        self._sessions[server_name] = session

        tools_result = await session.list_tools()
        for tool in tools_result.tools:
            registry_name, tool_obj, raw_schema = convert_mcp_tool(server_name, tool)
            self._tools[registry_name] = {
                "tool": tool_obj,
                "executor": make_mcp_executor(self.call_tool, server_name, tool.name),
                "input_schema": raw_schema,
            }

        resources_result = await session.list_resources()
        for resource in resources_result.resources:
            self._uri_map[str(resource.uri)] = server_name

    async def shutdown(self) -> None:
        await self._await_runner()
        self._sessions.clear()
        self._tools.clear()
        self._uri_map.clear()

    def get_tools(self) -> dict[str, dict]:
        return dict(self._tools)

    def get_server_statuses(self) -> dict[str, dict]:
        return dict(self._server_status)

    def get_resource_server(self, uri: str) -> str | None:
        return self._uri_map.get(uri)

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> ExecutorResult:
        session = self._sessions.get(server_name)
        if session is None:
            return ExecutorResult(
                display=f"MCP server '{server_name}' not available",
                content=f"Error: MCP server '{server_name}' is not connected.",
            )
        result = await session.call_tool(tool_name, arguments)
        content = "\n".join(block.text for block in result.content if block.type == "text")
        return ExecutorResult(display=content, content=content)

    async def read_resource(self, server_name: str, uri: str) -> ExecutorResult:
        session = self._sessions.get(server_name)
        if session is None:
            return ExecutorResult(
                display=f"MCP server '{server_name}' not available",
                content=f"Error: MCP server '{server_name}' is not connected.",
            )
        result = await session.read_resource(uri)  # type: ignore[arg-type]
        parts: list[str] = []
        for item in result.contents:
            if isinstance(item, TextResourceContents):
                parts.append(item.text)
            elif isinstance(item, BlobResourceContents):
                parts.append(item.blob)
        content = "\n".join(parts)
        return ExecutorResult(display=content, content=content)
