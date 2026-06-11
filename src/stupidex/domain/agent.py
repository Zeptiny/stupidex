from dataclasses import dataclass


@dataclass
class Agent:
    name: str
    description: str
    system_prompt: str
    available_tools: list[str]
