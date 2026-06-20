import asyncio
import json
import logging
import os
import random
import re
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import httpx
import litellm

from stupidex.config import HOME_CONFIG_DIR, get_config
from stupidex.domain.message import Message, MessageRole, MessageType, Usage
from stupidex.domain.session import get_current_session_id
from stupidex.domain.tool import ExecutorResult, Tool
from stupidex.llm.dynamic_system_prompt import build_dynamic_system_prompt
from stupidex.llm.providers import ProviderResolutionError, resolve_model_ref
from stupidex.llm.static_system_prompt import build_static_system_prompt
from stupidex.tools import get_tool_registry

log = logging.getLogger(__name__)

_YIELD_THROTTLE = 0.1
_TOOL_TIMEOUT = 60
_ERROR_DETAIL_MAX_LEN = 200
_TOOL_OUTPUT_INLINE_THRESHOLD = 10_000
_TOOLS_WITHOUT_OUTPUT_OFFLOAD = {
    "read",
    "grep",
    "glob",
    "directory_tree",
    "web_fetch",
}
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


def _tool_output_slug(tool_name: str, tool_call_id: str) -> str:
    raw = f"{tool_name}_{tool_call_id}"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("._-")
    slug = re.sub(r"_+", "_", slug)
    slug = (slug or "output")[:120]
    return f"{slug}.txt"


def _tool_output_cache_dir(session_id: str) -> Path:
    return HOME_CONFIG_DIR / "cache" / "tool-output" / session_id


def _maybe_offload_tool_output(
    tool_name: str, content: str, tool_call_id: str
) -> str:
    """Bound tool output size before it enters ``api_messages``.

    Outputs at or below ``_TOOL_OUTPUT_INLINE_THRESHOLD`` and tools that
    already self-limit (``_TOOLS_WITHOUT_OUTPUT_OFFLOAD``) pass through
    unchanged. Larger outputs are written to a per-session cache file
    (mirroring the web_fetch pattern) and replaced with a compact pointer
    so the provider context window is not blown out. When no session is
    active, the content is hard-truncated instead.
    """
    if (
        len(content) <= _TOOL_OUTPUT_INLINE_THRESHOLD
        or tool_name in _TOOLS_WITHOUT_OUTPUT_OFFLOAD
    ):
        return content

    session_id = get_current_session_id()
    if session_id is None:
        truncated = content[:_TOOL_OUTPUT_INLINE_THRESHOLD]
        return (
            f"<{tool_name}_result length={len(content)}>\n"
            f"<warning>Output exceeded {_TOOL_OUTPUT_INLINE_THRESHOLD} characters "
            f"and was truncated because no active session is available for cache "
            f"storage. Use the tool again with narrower scope (offset/limit) to "
            f"inspect the full result.</warning>\n{truncated}\n</{tool_name}_result>"
        )

    cache_dir = _tool_output_cache_dir(session_id)
    try:
        cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(cache_dir, 0o700)
        except OSError:
            log.debug("Failed to chmod tool-output cache dir %s", cache_dir, exc_info=True)
        path = cache_dir / _tool_output_slug(tool_name, tool_call_id)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        try:
            os.chmod(path, 0o600)
        except OSError:
            log.debug("Failed to chmod tool-output cache file %s", path, exc_info=True)
    except OSError as e:
        log.warning("Failed to offload tool output for %s: %s", tool_name, e, exc_info=True)
        truncated = content[:_TOOL_OUTPUT_INLINE_THRESHOLD]
        return (
            f"<{tool_name}_result length={len(content)}>\n"
            f"<warning>Output exceeded {_TOOL_OUTPUT_INLINE_THRESHOLD} characters "
            f"and cache write failed ({e}). Truncated below; re-run the tool with "
            f"narrower scope to inspect the full result.</warning>\n"
            f"{truncated}\n</{tool_name}_result>"
        )

    return (
        f"<{tool_name}_result length={len(content)} file=\"{path}\">\n"
        f"<warning>Output exceeded {_TOOL_OUTPUT_INLINE_THRESHOLD} characters and "
        f"was written to {path}. Use read (with offset/limit) or grep to inspect "
        f"it.</warning>\n</{tool_name}_result>"
    )


def _history_to_api_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert persisted display history to API history.

    Enforces the OpenAI-shaped invariant both ways:
    - every `tool` message is preceded by an assistant message whose
      `tool_calls` contains the same `tool_call_id` (orphaned tool results
      are dropped); and
    - every assistant `tool_calls` block has at least one following matching
      `tool` message (assistant tool_calls that never received a result --
      e.g. after an interrupted turn -- are filtered so we don't send
      dangling tool_calls, which would 400 on strict providers).
    """
    # Pre-pass: collect tool_call_ids that have a properly-sequenced matching
    # TOOL_RESULT — i.e. the result follows its preceding assistant tool_calls
    # block before any intervening non-thinking/non-tool message. Assistant
    # tool_calls entries whose ids have no *sequenced* result are filtered on
    # emit so we don't send a tool_calls block that never receives its tool
    # responses. A global "anywhere" presence check is too broad: it would
    # mark an id as surviving based on an orphan result that appears in a
    # later turn after the sequence was already broken, emitting a dangling
    # tool_calls block with no paired result in message order.
    surviving_tool_call_ids: set[str] = set()
    pending_tool_call_ids: set[str] = set()
    for msg in messages:
        if msg.type == MessageType.ERROR:
            continue
        if msg.type == MessageType.TOOL_CALL and not msg.tool_calls:
            continue
        if msg.type == MessageType.THINKING:
            # THINKING never breaks the tool_call/tool_result pairing (mirrors
            # the main loop's non-reset-on-thinking guarantee below).
            continue
        if msg.role == MessageRole.TOOL:
            if msg.tool_call_id and msg.tool_call_id in pending_tool_call_ids:
                surviving_tool_call_ids.add(msg.tool_call_id)
            continue
        if not msg.content and not msg.tool_calls:
            continue
        # An emitted non-tool message breaks the sequence: results from a
        # later turn can no longer legitimately pair with earlier tool_calls.
        # A new assistant tool_calls block resets pending to its own ids.
        pending_tool_call_ids = (
            {tc.get("id") for tc in msg.tool_calls if tc.get("id")}
            if msg.tool_calls
            else set()
        )

    api_messages: list[dict[str, Any]] = []
    last_assistant_tool_call_ids: set[str] = set()
    for msg in messages:
        if msg.type == MessageType.ERROR:
            continue
        if msg.type == MessageType.TOOL_CALL and not msg.tool_calls:
            continue
        if msg.type == MessageType.THINKING:
            # Replay THINKING as plain assistant content so reasoning-capable
            # models retain prior deliberation. The `reasoning` top-level
            # field is intentionally NOT emitted here: strict OpenAI Chat
            # Completions providers (gpt-4o etc.) reject unknown top-level
            # fields with HTTP 400. We pass the thinking text as `content`
            # because most providers tolerate it and it preserves context.
            # The match-set is NOT reset on THINKING: an intervening THINKING
            # between assistant(tool_calls=[A]) and tool(A) must not cause A
            # to be dropped as orphaned.
            if not msg.content:
                continue
            api_messages.append({
                "role": "assistant",
                "content": msg.content,
            })
            continue
        if msg.role == MessageRole.TOOL:
            if not msg.tool_call_id:
                continue
            if msg.tool_call_id not in last_assistant_tool_call_ids:
                log.debug(
                    "Dropping orphaned tool result for tool_call_id=%s "
                    "(no preceding assistant tool_calls message in history)",
                    msg.tool_call_id,
                )
                continue
            api_messages.append(msg.to_dict())
            continue
        if not msg.content and not msg.tool_calls:
            continue
        d = msg.to_dict()
        # Filter assistant tool_calls to only those that received a tool
        # result, and drop the field entirely if none survived. Avoids sending
        # dangling assistant tool_calls (e.g. after a cancelled turn) that
        # strict providers reject with 400.
        if msg.tool_calls:
            surviving = [
                tc for tc in msg.tool_calls
                if tc.get("id") in surviving_tool_call_ids
            ]
            if surviving:
                d["tool_calls"] = surviving
            else:
                d.pop("tool_calls", None)
                # If the assistant message has no content AND its tool_calls
                # were all unserviced, skip it entirely (empty assistant turn).
                if not msg.content:
                    last_assistant_tool_call_ids = set()
                    continue
        api_messages.append(d)
        if msg.tool_calls:
            last_assistant_tool_call_ids = {
                tc.get("id") for tc in msg.tool_calls if tc.get("id")
            }
        else:
            last_assistant_tool_call_ids = set()
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


_BACKOFF_BASE = 0.2


class _StreamIdleTimeoutError(Exception):
    """Raised when the LLM stream produces no chunk for the configured idle timeout.

    The timeout is scoped to the streaming loop only — it measures
    time-since-last-delta-received and is reset on every chunk. Tool-execution
    time (which happens outside the stream iteration, in ``_executor_task``)
    does NOT count against it. A retry with exponential backoff is attempted up
    to ``cfg.llm_stream_retries`` times before this propagates to the caller.
    """

    def __init__(self, idle_timeout: float) -> None:
        super().__init__(
            f"LLM stream was idle for more than {idle_timeout:.1f}s with no deltas"
        )


async def _safe_aclose(response: Any) -> None:
    """Best-effort ``aclose()`` on a streaming response object.

    Ensures the underlying HTTP stream is released on timeout/retry/finish
    (addresses the P1-10 stream-leak concern). Litellm streaming responses are
    async generators that expose ``aclose()``; fake/test iterables may not, so
    the attribute is checked dynamically.
    """
    aclose = getattr(response, "aclose", None)
    if aclose is None:
        return
    try:
        await aclose()
    except Exception:
        log.debug("aclose() on stream response failed", exc_info=True)


async def _idle_timed_stream(response: Any, idle_timeout: float) -> AsyncGenerator[Any, None]:
    """Re-yield chunks from ``response`` with a per-chunk idle deadline.

    The deadline is measured from the last received chunk — each chunk resets
    the timer. If no chunk arrives within ``idle_timeout`` seconds,
    ``_StreamIdleTimeoutError`` is raised after the underlying response is closed.
    """
    try:
        while True:
            try:
                chunk = await asyncio.wait_for(
                    response.__anext__(), timeout=idle_timeout
                )
            except StopAsyncIteration:
                return
            except TimeoutError:
                await _safe_aclose(response)
                raise _StreamIdleTimeoutError(idle_timeout) from None
            yield chunk
    finally:
        await _safe_aclose(response)


async def _backoff_sleep(attempt: int) -> None:
    """Exponential backoff with jitter between stream-idle retries."""
    delay = _BACKOFF_BASE * (2 ** attempt)
    jitter = random.uniform(0, _BACKOFF_BASE)
    await asyncio.sleep(delay + jitter)


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
        enqueued_tool_calls: set[int] = set()
        usage = None
        last_thinking_yield: float = 0
        thinking_dirty: bool = False
        prev_index: int | None = None
        assistant_api_msg: dict[str, Any] | None = None

        async def flush_thinking() -> None:
            nonlocal thinking_dirty, last_thinking_yield
            if not thinking_dirty:
                return
            last_thinking_yield = time.monotonic()
            thinking_dirty = False
            if thinking.strip():
                await msg_q.put(Message(
                    role=MessageRole.ASSISTANT,
                    content=thinking,
                    type=MessageType.THINKING,
                ))

        async def commit_assistant_with_tool_calls() -> None:
            """Anchor the assistant tool_calls block once.

            Appends the assistant message to the ephemeral `api_messages`
            (so the executor sees it follow by its tool results in the same
            list), signals `assistant_appended` so the executor is unblocked,
            marks `tool_calls_started` so the end-of-stream flush knows not
            to repeat this, and emits the same assistant message through
            `msg_q` so record_streamed_message persists it on disk.

            Called at most once per stream: at the first mid-stream index
            transition (multi-tool) or at end-of-stream (single tool).
            Subsequent transitions re-use the same anchored assistant entry;
            the live `tool_calls` list continues to grow as more deltas
            arrive and the persisted history's reference sees those
            additions because we share the list, not snapshot it.

            Tool-call entries lacking an `id` or `function.name` (placeholders
            that never received their identifying delta) are dropped before
            anchoring so strict providers don't 400 on an empty id/name. If
            none survive the filter, an empty-assistant (content-only, no
            tool_calls) message is anchored instead. The live `tool_calls`
            list is filtered in place so the reference shared with the
            anchored assistant dict/Message keeps growing as later deltas
            append well-formed entries.
            """
            nonlocal assistant_api_msg
            tool_calls[:] = [
                tc for tc in tool_calls
                if tc.get("id") and tc["function"].get("name")
            ]
            if tool_calls:
                assistant_api_msg = {
                    "role": "assistant",
                    "content": content or None,
                    "tool_calls": tool_calls,
                }
                api_messages.append(assistant_api_msg)
                assistant_appended.set()
                tool_calls_started.set()
                await msg_q.put(Message(
                    role=MessageRole.ASSISTANT,
                    content=content,
                    type=MessageType.TEXT,
                    tool_calls=tool_calls,
                ))
            else:
                assistant_api_msg = {"role": "assistant", "content": content or None}
                api_messages.append(assistant_api_msg)
                assistant_appended.set()
                tool_calls_started.set()
                if content:
                    await msg_q.put(Message(
                        role=MessageRole.ASSISTANT,
                        content=content,
                        type=MessageType.TEXT,
                    ))

        async def emit_malformed_tool_call(prev_idx: int) -> None:
            await msg_q.put(Message(
                role=MessageRole.ASSISTANT,
                content=(
                    f"Malformed tool call: missing id or name for tool_call index {prev_idx}"
                ),
                type=MessageType.ERROR,
                metadata={"error_title": "Malformed Tool Call"},
            ))

        async def maybe_enqueue(prev_idx: int) -> None:
            if prev_idx in enqueued_tool_calls:
                return
            if prev_idx >= len(tool_calls):
                await emit_malformed_tool_call(prev_idx)
                enqueued_tool_calls.add(prev_idx)
                return
            tc = tool_calls[prev_idx]
            tc_id = tc.get("id")
            tc_name = tc["function"].get("name")
            if not tc_id or not tc_name:
                await emit_malformed_tool_call(prev_idx)
                enqueued_tool_calls.add(prev_idx)
                return
            enqueued_tool_calls.add(prev_idx)
            await ready_q.put(tc)

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
                    if thinking.strip():
                        await msg_q.put(Message(
                            role=MessageRole.ASSISTANT,
                            content=thinking,
                            type=MessageType.THINKING,
                        ))
                else:
                    thinking_dirty = True

            if delta.content:
                await flush_thinking()
                content += delta.content
                if assistant_api_msg is not None:
                    assistant_api_msg["content"] = content
                if not tool_calls_started.is_set():
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
                            await commit_assistant_with_tool_calls()
                        await maybe_enqueue(prev_index)
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
                await commit_assistant_with_tool_calls()
            if usage:
                await msg_q.put(Message(role=MessageRole.ASSISTANT, content="", usage=usage))
            await maybe_enqueue(prev_index)

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
            trimmed = _maybe_offload_tool_output(
                tc["function"]["name"], result_msg.content, tc["id"]
            )
            api_messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": trimmed,
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

    idle_timeout = cfg.llm_stream_idle_timeout
    retries = max(0, cfg.llm_stream_retries)

    while True:
        attempt = 0
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
                _idle_timed_stream(response, idle_timeout),
                msg_q, ready_q, api_messages, assistant_appended, tool_calls_started,
            ))
            executor_t = asyncio.create_task(_executor_task(
                msg_q, ready_q, api_messages, filtered_tools, assistant_appended,
            ))

            try:
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
            except _StreamIdleTimeoutError:
                if attempt < retries:
                    log.warning(
                        "LLM stream idle for >%.1fs; retry %d/%d",
                        idle_timeout, attempt + 1, retries,
                    )
                    await _backoff_sleep(attempt)
                    attempt += 1
                    continue
                raise
            break

        if not tool_calls_started.is_set():
            return
