import json
from collections.abc import Generator

import litellm

from stupidex.domain.message import Message, MessageRole, MessageType, Usage
from stupidex.llm.static_system_prompt import build_static_system_prompt
from stupidex.llm.dynamic_system_prompt import build_dynamic_system_prompt
from stupidex.domain.tool import ExecutorResult
from stupidex.tools import TOOL_REGISTRY


def stream_response(messages: list[Message], model: str | None) -> Generator[Message, None, None]:
    api_messages = [build_static_system_prompt().to_dict()] + \
        [m.to_dict() for m in messages] + \
        [build_dynamic_system_prompt().to_dict()]

    tools_list = [entry["tool"].to_dict() for entry in TOOL_REGISTRY.values()]

    while True:
        response = litellm.completion(
            model="openai/" + model,
            messages=api_messages,
            tools=tools_list,
            base_url="https://opencode.ai/zen/go/v1",
            stream=True,
            stream_options={"include_usage": True},
        )

        thinking = ""
        content = ""
        tool_calls: list[dict] = []
        usage = None

        for chunk in response:
            delta = chunk.choices[0].delta

            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                thinking += delta.reasoning_content
                yield Message(
                    role=MessageRole.ASSISTANT,
                    content=thinking,
                    type=MessageType.THINKING,
                )

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

            if hasattr(chunk, "usage") and chunk.usage:
                usage = Usage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    total_tokens=chunk.usage.total_tokens,
                )

        if not tool_calls:
            yield Message(role=MessageRole.ASSISTANT, content=content, usage=usage)
            return

        assistant_msg: dict = {"role": "assistant",
                               "content": content or None, "tool_calls": tool_calls}
        api_messages.append(assistant_msg)

        for tc in tool_calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"])
            if name not in TOOL_REGISTRY:
                result = ExecutorResult(
                    display=f"Unknown tool: {name}",
                    content=f"Error: tool '{name}' does not exist. Available tools: {', '.join(TOOL_REGISTRY)}",
                )
            else:
                executor = TOOL_REGISTRY[name]["executor"]
                result = executor(**args)

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
