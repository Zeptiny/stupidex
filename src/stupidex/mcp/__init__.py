from __future__ import annotations

import asyncio
import contextlib
import logging
from contextvars import ContextVar

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

    The ``stdio_client`` / ``sse_client`` transports wrap ``anyio`` task groups
    whose cancel scopes are task-bound: the task that *enters* a transport
    context must be the one that *exits* it. In the app, ``start_all`` runs from
    ``App.on_mount`` and ``shutdown`` from ``App.on_exit`` — Textual dispatches
    these in different tasks. To keep the enter/exit pair on a single task, the
    whole lifecycle (enter transports, then later close them) runs inside one
    dedicated runner task that owns the :class:`AsyncExitStack`.
    """

    def __init__(self):
        self._exit_stack = contextlib.AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}
        self._tools: dict[str, dict] = {}
        self._uri_map: dict[str, str] = {}  # uri -> server_name
        self._server_status: dict[str, dict] = {}  # name -> {status, tool_count, error}
        self._runner: asyncio.Task | None = None
        self._ready: asyncio.Event = asyncio.Event()
        self._stop: asyncio.Event = asyncio.Event()
        self._start_error: BaseException | None = None

    async def start_all(self, servers: dict[str, dict]) -> None:
        if self._runner is not None and not self._runner.done():
            raise RuntimeError("MCPManager.start_all already in progress")
        # Reinitialize the one-shot lifecycle state so a manager can be
        # restarted after shutdown: the Events were set by the prior run and
        # the exit stack was closed by shutdown, which would otherwise make the
        # second start return before the runner enters any transport.
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._start_error = None
        self._exit_stack = contextlib.AsyncExitStack()
        for server_name in servers:
            self._server_status[server_name] = {"status": "starting", "tool_count": 0, "error": None}
        # The runner owns the exit stack; transports are entered AND exited in
        # this task, avoiding anyio's cross-task cancel-scope error.
        self._runner = asyncio.create_task(self._run(servers))
        await self._ready.wait()
        if self._start_error is not None:
            # Startup itself failed; ensure the runner has torn down.
            await self._await_runner()
            raise self._start_error

    async def _run(self, servers: dict[str, dict]) -> None:
        try:
            await self._exit_stack.__aenter__()
            for server_name, config in servers.items():
                try:
                    await self._start_server(server_name, config)
                    tool_count = sum(1 for k in self._tools if k.startswith(f"mcp_{server_name}_"))
                    self._server_status[server_name] = {"status": "connected", "tool_count": tool_count, "error": None}
                except Exception as e:
                    self._server_status[server_name] = {"status": "failed", "tool_count": 0, "error": str(e)[:80]}
                    logger.warning("Failed to start MCP server '%s'", server_name, exc_info=True)
        except BaseException as e:
            # Captured so start_all can re-raise after the runner unwinds.
            self._start_error = e
        finally:
            self._ready.set()
            # Idle until shutdown is requested, then close the stack in THIS
            # task — the same task that entered every transport.
            # Catch CancelledError so aclose() runs regardless — otherwise
            # the async generators (stdio_client, sse_client) dangle and
            # their finalizers later raise "exit cancel scope in a different
            # task" when the event loop runs shutdown_asyncgens.
            cancelled: bool = False
            try:
                await self._stop.wait()
            except asyncio.CancelledError:
                cancelled = True
            try:
                await self._exit_stack.aclose()
            except Exception:
                logger.warning("Error during MCP shutdown", exc_info=True)
            if cancelled:
                raise

    async def _await_runner(self, timeout: float = 3.0) -> None:
        self._stop.set()
        runner = self._runner
        if runner is not None:
            try:
                await asyncio.wait_for(runner, timeout=timeout)
            except TimeoutError:
                runner.cancel()
                logger.warning("MCP shutdown timed out after %.1fs, cancelling runner", timeout)
                try:
                    await runner
                except asyncio.CancelledError:
                    pass
            except Exception:
                logger.warning("MCP runner task ended with an error", exc_info=True)
        self._runner = None

    async def _start_server(self, server_name: str, config: dict) -> None:
        from stupidex.mcp.schema import convert_mcp_tool, make_mcp_executor

        if "url" in config:
            read_stream, write_stream = await self._exit_stack.enter_async_context(sse_client(url=config["url"]))
        else:
            server_params = StdioServerParameters(
                command=config["command"],
                args=config.get("args", []),
                env=config.get("env"),
            )
            read_stream, write_stream = await self._exit_stack.enter_async_context(stdio_client(server_params))

        session: ClientSession = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
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
