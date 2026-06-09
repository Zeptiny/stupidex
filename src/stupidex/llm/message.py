from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rich.markdown import Markdown
from rich.panel import Panel


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
        """Convert to LLM API format."""
        return {"role": self.role.value, "content": self.content}

    def render(self) -> Panel | Markdown:
        """Render for display."""
        match self.type:
            case MessageType.THINKING:
                return Panel(Markdown(f"*{self.content}*"), style="dim")
            case MessageType.TOOL_CALL:
                tool = self.metadata.get("tool_name", "unknown")
                return Panel(Markdown(f"`{tool}`"), title="Tool Call", style="blue")
            case MessageType.TOOL_RESULT:
                return Panel(self.content, title="Tool Result", style="blue")
            case _:
                if self.role == MessageRole.USER:
                    return Panel(Markdown(self.content), style="green")
                return Panel(Markdown(self.content)) # Default style for assistant and system messages
