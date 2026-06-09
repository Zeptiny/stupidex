import litellm
from collections.abc import Generator

from .message import Message, MessageRole, MessageType

chat_history: list[Message] = []


def stream_input(user_input: str) -> Generator[Message, None, None]:
    chat_history.append(Message(role=MessageRole.USER, content=user_input))

    response = litellm.completion(
        model="openai/deepseek-v4-flash",
        messages=[m.to_dict() for m in chat_history],
        base_url="https://opencode.ai/zen/go/v1",
        stream=True,
    )

    thinking = ""
    content = ""
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

    chat_history.append(Message(role=MessageRole.ASSISTANT, content=content))