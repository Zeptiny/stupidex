import litellm

chat_history: list[dict] = []


def handle_input(user_input: str) -> str:
    chat_history.append({"role": "user", "content": user_input})

    response = litellm.completion(
        model="openai/deepseek-v4-flash",
        messages=chat_history,
        base_url="https://opencode.ai/zen/go/v1"
    )

    assistant_msg = response.choices[0].message.content
    chat_history.append({"role": "assistant", "content": assistant_msg})
    return assistant_msg