import litellm
from collections.abc import Generator

from .message import Message, MessageRole, MessageType, Usage

chat_history: list[Message] = []


def stream_input(user_input: str) -> Generator[Message, None, None]:
    chat_history.append(Message(role=MessageRole.USER, content=user_input))

    response = litellm.completion(
        model="openai/deepseek-v4-flash",
        messages=[m.to_dict() for m in chat_history],
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
                total_tokens=chunk.usage.total_tokens
            )

    final_msg = Message(role=MessageRole.ASSISTANT, content=content, usage=usage)
    chat_history.append(final_msg)
    yield final_msg