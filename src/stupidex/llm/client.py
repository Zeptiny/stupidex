import json
import time
from collections.abc import AsyncGenerator

import litellm

from stupidex.config import get_config
from stupidex.domain.message import Message, MessageRole, MessageType, Usage
from stupidex.domain.tool import ExecutorResult
from stupidex.llm.dynamic_system_prompt import build_dynamic_system_prompt
from stupidex.llm.static_system_prompt import build_static_system_prompt
from stupidex.tools import get_tool_registry

_YIELD_THROTTLE = 0.1


async def stream_response(
    messages: list[Message],
    model: str | None,
    available_tools: list[str],
    system_prompt: str,
) -> AsyncGenerator[Message, None]:
    cfg = get_config()
    system_msg = build_static_system_prompt(system_prompt)
    api_messages = [system_msg.to_dict()] + \
        [m.to_dict() for m in messages] + \
        [build_dynamic_system_prompt().to_dict()]

    registry = get_tool_registry()
    filtered_tools = {k: v for k, v in registry.items()
                      if k in available_tools}
    tools_list = [entry["tool"].to_dict() for entry in filtered_tools.values()]

    while True:
        response = await litellm.acompletion(
            model=cfg.provider_api_type + "/" + (model or cfg.default_model),
            messages=api_messages,
            tools=tools_list,
            base_url=cfg.base_url,
            stream=True,
            stream_options={"include_usage": True},
        )

        thinking = ""
        content = ""
        tool_calls: list[dict] = []
        emitted_tool_calls: set[int] = set()
        usage = None
        last_thinking_yield: float = 0
        thinking_dirty: bool = False

        async for chunk in response:
            delta = chunk.choices[0].delta

            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                thinking += delta.reasoning_content
                now = time.monotonic()
                if now - last_thinking_yield >= _YIELD_THROTTLE:
                    last_thinking_yield = now
                    thinking_dirty = False
                    yield Message(
                        role=MessageRole.ASSISTANT,
                        content=thinking,
                        type=MessageType.THINKING,
                    )
                else:
                    thinking_dirty = True

            if delta.content:
                content += delta.content
                yield Message(
                    role=MessageRole.ASSISTANT,
                    content=content,
                    type=MessageType.TEXT,
                )

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
                        emitted_tool_calls.add(tc_delta.index)
                        yield Message(
                            role=MessageRole.ASSISTANT,
                            content=f"Calling tool: {tc['function']['name']}",
                            type=MessageType.TOOL_CALL,
                            metadata={"tool_name": tc["function"]["name"]},
                        )

            if hasattr(chunk, "usage") and chunk.usage:
                usage = Usage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                )

        if thinking_dirty:
            yield Message(
                role=MessageRole.ASSISTANT,
                content=thinking,
                type=MessageType.THINKING,
            )

        if not tool_calls:
            yield Message(role=MessageRole.ASSISTANT, content=content, usage=usage)
            return

        if usage:
            yield Message(role=MessageRole.ASSISTANT, content="", usage=usage)

        assistant_msg: dict = {"role": "assistant",
                               "content": content or None, "tool_calls": tool_calls}
        api_messages.append(assistant_msg)

        for tc in tool_calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"])

            if name not in filtered_tools:
                result = ExecutorResult(
                    display=f"Unknown tool: {name}",
                    content=f"Error: tool '{name}' does not exist. Available tools: {', '.join(filtered_tools.keys())}",
                )
            else:
                executor = filtered_tools[name]["executor"]
                result = await executor(**args)

            # Yield a TOOL_RESULT message with the execution result
            yield Message(
                role=MessageRole.TOOL,
                content=result.content,
                display=result.display,
                type=MessageType.TOOL_RESULT,
                tool_call_id=tc["id"],
            )

            api_messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result.content,
            })
