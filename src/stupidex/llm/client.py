import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import litellm

from stupidex.config import get_config
from stupidex.domain.message import Message, MessageRole, MessageType, Usage
from stupidex.domain.tool import ExecutorResult, Tool
from stupidex.llm.dynamic_system_prompt import build_dynamic_system_prompt
from stupidex.llm.providers import ProviderResolutionError, resolve_model_ref
from stupidex.llm.static_system_prompt import build_static_system_prompt
from stupidex.tools import get_tool_registry

log = logging.getLogger(__name__)

_YIELD_THROTTLE = 0.1
_TOOL_TIMEOUT = 60
_ERROR_DETAIL_MAX_LEN = 200
_TOOLS_WITHOUT_TIMEOUT = {
    "wait_for_subagent",
    "get_file_skeleton",
    "get_function",
    "find_symbol_references",
    "replace_symbol",
    "rename_symbol",
}


def classify_error(exc: Exception) -> tuple[str, str]:
    """Map an exception to a (title, detail) pair for user-facing display."""
    detail = str(exc)[:_ERROR_DETAIL_MAX_LEN] or type(exc).__name__
    if isinstance(exc, ProviderResolutionError):
        return (
            "Unknown Provider",
            detail or "The model reference could not be resolved. Check your providers config.",
        )
    if isinstance(exc, litellm.AuthenticationError):
        return "Authentication Failed", "Invalid or missing API key. Check your configuration."
    if isinstance(exc, litellm.RateLimitError):
        return "Rate Limit Exceeded", "Too many requests. Please wait and try again."
    if isinstance(exc, litellm.Timeout):
        return "Request Timed Out", "The API did not respond in time. Try again later."
    if isinstance(exc, litellm.APIConnectionError):
        return "Connection Failed", "Could not reach the API server. Check your network and base_url."
    if isinstance(exc, litellm.BadRequestError):
        return "Invalid Request", detail or "The request was rejected by the API."
    if isinstance(exc, litellm.InternalServerError):
        return "Server Error", detail or "The API server encountered an internal error."
    if isinstance(exc, litellm.ServiceUnavailableError):
        return "Service Unavailable", detail or "The API service is temporarily unavailable."
    if isinstance(exc, litellm.BadGatewayError):
        return "Bad Gateway", detail or "The API server returned a bad gateway error."
    if isinstance(exc, litellm.APIError):
        return "API Error", detail or "The API returned an error."
    if isinstance(exc, httpx.TimeoutException):
        return "Request Timed Out", "The API did not respond in time. Try again later."
    if isinstance(exc, httpx.HTTPError):
        return "HTTP Error", detail or "An HTTP error occurred."
    return "Unexpected Error", detail


def _raise_first_task_exception(results: tuple[Any, ...]) -> None:
    """Re-raise the first non-cancellation exception from gathered task results."""
    for r in results:
        if isinstance(r, BaseException) and not isinstance(r, asyncio.CancelledError):
            raise r


def _validate_tool_args(tool: Tool, args: dict) -> str | None:
    """Return error message if args are invalid, None if ok."""
    known = set(tool.parameters.properties.keys())
    unknown = set(args.keys()) - known
    if unknown:
        return f"Unknown parameters: {', '.join(sorted(unknown))}. Expected: {', '.join(sorted(known))}"
    for req in tool.parameters.required:
        if req not in args:
            return f"Missing required parameter: {req}"
    return None


def _history_to_api_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert persisted display history to API history."""
    api_messages = []
    for msg in messages:
        if msg.type in (MessageType.THINKING, MessageType.TOOL_CALL, MessageType.TOOL_RESULT, MessageType.ERROR):
            continue
        if not msg.content and not msg.tool_calls:
            continue
        api_messages.append(msg.to_dict())
    return api_messages


async def _execute_tool(
    tc: dict,
    filtered_tools: dict[str, dict[str, Any]],
) -> Message:
    """Execute a single tool call and return the result message."""
    name = tc["function"]["name"]

    try:
        args = json.loads(tc["function"]["arguments"])
    except json.JSONDecodeError:
        result = ExecutorResult(
            display=f"Invalid arguments for {name}",
            content=f"Error: Could not parse arguments for tool '{name}': invalid JSON.",
        )
    else:
        if not isinstance(args, dict):
            result = ExecutorResult(
                display=f"Invalid arguments for {name}",
                content=f"Error: Arguments for tool '{name}' must be a JSON object, got {type(args).__name__}.",
            )
        elif name not in filtered_tools:
            result = ExecutorResult(
                display=f"Unknown tool: {name}",
                content=f"Error: tool '{name}' does not exist. Available tools: {', '.join(filtered_tools.keys())}",
            )
        else:
            tool_def = filtered_tools[name]["tool"]
            validation_error = _validate_tool_args(tool_def, args)
            if validation_error:
                result = ExecutorResult(
                    display=f"Invalid args for {name}",
                    content=f"Error: {validation_error}",
                )
            else:
                executor = filtered_tools[name]["executor"]
                try:
                    if name in _TOOLS_WITHOUT_TIMEOUT:
                        result = await executor(**args)
                    else:
                        result = await asyncio.wait_for(executor(**args), timeout=_TOOL_TIMEOUT)
                except TimeoutError:
                    result = ExecutorResult(
                        display=f"Timeout in {name}",
                        content=f"Tool '{name}' timed out after {_TOOL_TIMEOUT}s.",
                    )
                except Exception:
                    log.exception("Tool '%s' raised an exception", name)
                    result = ExecutorResult(
                        display=f"Error in {name}",
                        content=f"Tool '{name}' failed with an internal error.",
                    )

    return Message(
        role=MessageRole.TOOL,
        content=result.content,
        display=result.display,
        type=MessageType.TOOL_RESULT,
        tool_call_id=tc["id"],
    )


async def _stream_task(
    response: Any,
    msg_q: asyncio.Queue[Message | None],
    ready_q: asyncio.Queue[dict | None],
    api_messages: list[dict[str, Any]],
    assistant_appended: asyncio.Event,
    tool_calls_started: asyncio.Event,
) -> None:
    """Consume the LLM stream, yield messages to msg_q, and queue tools to ready_q."""
    try:
        thinking = ""
        content = ""
        tool_calls: list[dict] = []
        emitted_tool_calls: set[int] = set()
        usage = None
        last_thinking_yield: float = 0
        thinking_dirty: bool = False
        prev_index: int | None = None

        async def flush_thinking() -> None:
            nonlocal thinking_dirty, last_thinking_yield
            if not thinking_dirty:
                return
            last_thinking_yield = time.monotonic()
            thinking_dirty = False
            stripped = thinking.strip()
            if stripped:
                await msg_q.put(Message(
                    role=MessageRole.ASSISTANT,
                    content=stripped,
                    type=MessageType.THINKING,
                ))

        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                thinking += delta.reasoning_content
                now = time.monotonic()
                if now - last_thinking_yield >= _YIELD_THROTTLE:
                    last_thinking_yield = now
                    thinking_dirty = False
                    stripped = thinking.strip()
                    if stripped:
                        await msg_q.put(Message(
                            role=MessageRole.ASSISTANT,
                            content=stripped,
                            type=MessageType.THINKING,
                        ))
                else:
                    thinking_dirty = True

            if delta.content:
                await flush_thinking()
                content += delta.content
                await msg_q.put(Message(
                    role=MessageRole.ASSISTANT,
                    content=content,
                    type=MessageType.TEXT,
                ))

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    while tc_delta.index >= len(tool_calls):
                        tool_calls.append({"id": "", "type": "function", "function": {
                                          "name": "", "arguments": ""}})
                    tc = tool_calls[tc_delta.index]
                    if tc_delta.id:
                        tc["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tc["function"]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tc["function"]["arguments"] += tc_delta.function.arguments

                    if tc["function"]["name"] and tc_delta.index not in emitted_tool_calls:
                        await flush_thinking()
                        emitted_tool_calls.add(tc_delta.index)
                        await msg_q.put(Message(
                            role=MessageRole.ASSISTANT,
                            content=f"Calling tool: {tc['function']['name']}",
                            type=MessageType.TOOL_CALL,
                            metadata={"tool_name": tc["function"]["name"]},
                        ))

                    if prev_index is not None and prev_index != tc_delta.index:
                        await flush_thinking()
                        if not tool_calls_started.is_set():
                            api_messages.append({"role": "assistant",
                                                 "content": content or None, "tool_calls": tool_calls})
                            assistant_appended.set()
                            tool_calls_started.set()
                        await ready_q.put(tool_calls[prev_index])
                    prev_index = tc_delta.index

            if hasattr(chunk, "usage") and chunk.usage:
                usage = Usage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                )

        await flush_thinking()

        if prev_index is not None:
            if not tool_calls_started.is_set():
                api_messages.append({"role": "assistant",
                                     "content": content or None, "tool_calls": tool_calls})
                assistant_appended.set()
                tool_calls_started.set()
            if usage:
                await msg_q.put(Message(role=MessageRole.ASSISTANT, content="", usage=usage))
            await ready_q.put(tool_calls[prev_index])

        if not tool_calls and usage:
            await msg_q.put(Message(role=MessageRole.ASSISTANT, content="", usage=usage))
    finally:
        await ready_q.put(None)


async def _executor_task(
    msg_q: asyncio.Queue[Message | None],
    ready_q: asyncio.Queue[dict | None],
    api_messages: list[dict[str, Any]],
    filtered_tools: dict[str, dict[str, Any]],
    assistant_appended: asyncio.Event,
) -> None:
    """Execute tools sequentially as they become ready, yielding results to msg_q."""
    try:
        while True:
            tc = await ready_q.get()
            if tc is None:
                break
            result_msg = await _execute_tool(tc, filtered_tools)
            await msg_q.put(result_msg)
            await assistant_appended.wait()
            api_messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result_msg.content,
            })
    finally:
        await msg_q.put(None)


async def stream_response(
    messages: list[Message],
    model: str | None,
    allowed_tools: list[str],
    system_prompt: str,
    allowed_skills: list[str] | None = None,
) -> AsyncGenerator[Message, None]:
    from stupidex.tools.skill import set_current_allowed_skills
    set_current_allowed_skills(allowed_skills)

    cfg = get_config()
    system_msg = build_static_system_prompt(system_prompt)
    dynamic_prompt = await build_dynamic_system_prompt()
    api_messages: list[dict[str, Any]] = [system_msg.to_dict()] + \
        _history_to_api_messages(messages) + \
        [dynamic_prompt.to_dict()]

    registry = get_tool_registry()
    from fnmatch import fnmatch
    filtered_tools = {k: v for k, v in registry.items()
                      if any(fnmatch(k, p) for p in allowed_tools)}

    from stupidex.mcp import get_mcp_manager
    mcp_manager = get_mcp_manager()
    if mcp_manager is not None:
        for name, tool_entry in mcp_manager.get_tools().items():
            if any(fnmatch(name, p) for p in allowed_tools):
                filtered_tools[name] = tool_entry

    tools_list = [entry["tool"].to_dict() for entry in filtered_tools.values()]

    litellm_provider, model_id, base_url, api_key = resolve_model_ref(
        model or cfg.default_model
    )
    litellm_model = f"{litellm_provider}/{model_id}" if litellm_provider else model_id

    while True:
        response = await litellm.acompletion(
            model=litellm_model,
            messages=api_messages,
            tools=tools_list,
            base_url=base_url,
            api_key=api_key,
            stream=True,
            stream_options={"include_usage": True},
        )

        msg_q: asyncio.Queue[Message | None] = asyncio.Queue(maxsize=1)
        ready_q: asyncio.Queue[dict | None] = asyncio.Queue()
        assistant_appended = asyncio.Event()
        tool_calls_started = asyncio.Event()

        stream_t = asyncio.create_task(_stream_task(
            response, msg_q, ready_q, api_messages, assistant_appended, tool_calls_started,
        ))
        executor_t = asyncio.create_task(_executor_task(
            msg_q, ready_q, api_messages, filtered_tools, assistant_appended,
        ))

        try:
            while True:
                msg = await msg_q.get()
                if msg is None:
                    break
                yield msg
        except asyncio.CancelledError:
            stream_t.cancel()
            executor_t.cancel()
            _raise_first_task_exception(
                await asyncio.gather(stream_t, executor_t, return_exceptions=True))
            raise
        except BaseException:
            stream_t.cancel()
            executor_t.cancel()
            _raise_first_task_exception(
                await asyncio.gather(stream_t, executor_t, return_exceptions=True))
            raise
        else:
            _raise_first_task_exception(
                await asyncio.gather(stream_t, executor_t, return_exceptions=True))

        if not tool_calls_started.is_set():
            return
