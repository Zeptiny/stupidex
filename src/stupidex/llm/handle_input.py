import litellm
from collections.abc import Generator

chat_history: list[dict] = []


def stream_input(user_input: str) -> Generator[str, None, None]:
    chat_history.append({"role": "user", "content": user_input})

    response = litellm.completion(
        model="openai/deepseek-v4-flash",
        messages=chat_history,
        base_url="https://opencode.ai/zen/go/v1",
        stream=True,
    )

    full_response = ""
    for chunk in response:
        delta = chunk.choices[0].delta.content or ""
        full_response += delta
        yield delta

    chat_history.append({"role": "assistant", "content": full_response})