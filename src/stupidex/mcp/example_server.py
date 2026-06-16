"""Minimal example MCP server demonstrating tool + resource usage.

Run standalone: python -m stupidex.mcp.example_server
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from mcp.server.lowlevel import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server
from mcp.types import Resource, TextContent, Tool
from pydantic import AnyUrl

server = Server("stupidex-example")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="echo",
            description="Echoes the input message back to the caller",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "The message to echo"},
                },
                "required": ["message"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "echo":
        return [TextContent(type="text", text=arguments.get("message", ""))]
    raise ValueError(f"Unknown tool: {name}")


@server.list_resources()
async def list_resources() -> list[Resource]:
    return [
        Resource(
            uri=AnyUrl("info://stupidex"),
            name="App Info",
            description="Basic information about the stupidex application",
            mimeType="text/plain",
        )
    ]


@server.read_resource()
async def read_resource(uri: AnyUrl) -> Iterable[ReadResourceContents]:
    if str(uri) == "info://stupidex":
        return [ReadResourceContents(
            content="stupidex is a coding CLI with MCP support",
            mime_type="text/plain",
        )]
    raise ValueError(f"Unknown resource: {uri}")


async def _run() -> None:
    async with stdio_server() as (read_stream, write_stream):
        init_options = server.create_initialization_options()
        await server.run(read_stream, write_stream, init_options)


if __name__ == "__main__":
    asyncio.run(_run())
