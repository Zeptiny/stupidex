import litellm

def handle_input(user_input: str) -> str:
    # Process the user input and generate a response
    response = litellm.completion(
        model="openai/deepseek-v4-flash",
        messages=[
            {"role": "user", "content": [{"type": "text", "text": user_input}]}
        ],
        base_url="https://opencode.ai/zen/go/v1"
    )
    return response.choices[0].message.content