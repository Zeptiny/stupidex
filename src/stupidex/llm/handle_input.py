import litellm
from collections.abc import Generator

from .message import Message, MessageRole, MessageType, Usage


def stream_response(messages: list[Message]) -> Generator[Message, None, None]:
    response = litellm.completion(
        model="openai/mimo-v2.5",
        messages=[m.to_dict() for m in messages],
        base_url="https://opencode.ai/zen/go/v1",
        stream=True,
        stream_options={"include_usage": True},
    )

    thinking = ""
    content = ""
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

        if hasattr(chunk, "usage") and chunk.usage:
            usage = Usage(
                prompt_tokens=chunk.usage.prompt_tokens,
                completion_tokens=chunk.usage.completion_tokens,
                total_tokens=chunk.usage.total_tokens,
            )

    yield Message(role=MessageRole.ASSISTANT, content=content, usage=usage)