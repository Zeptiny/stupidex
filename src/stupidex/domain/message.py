from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class MessageType(Enum):
    TEXT = "text"
    THINKING = "thinking"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"


@dataclass
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class Message:
    role: MessageRole
    content: str
    type: MessageType = MessageType.TEXT
    metadata: dict[str, Any] = field(default_factory=dict)
    usage: Usage | None = None

    def to_dict(self) -> dict[str, str]:
        return {"role": self.role.value, "content": self.content}
