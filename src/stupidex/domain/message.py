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
    display: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    usage: Usage | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role.value, "content": self.content}
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        return d


@dataclass
class StreamHistoryState:
    """Tracks persisted messages while cumulative stream snapshots arrive."""
    thinking: Message | None = None
    content: Message | None = None


def record_streamed_message(history: list[Message], msg: Message, state: StreamHistoryState) -> bool:
    """Record a streamed message without persisting duplicate cumulative snapshots."""
    if msg.type == MessageType.THINKING:
        if state.thinking is None:
            history.append(msg)
            state.thinking = msg
            return True
        state.thinking.content = msg.content
        if msg.usage:
            state.thinking.usage = msg.usage
        return False

    if msg.type == MessageType.TOOL_CALL:
        return False

    if msg.type == MessageType.TOOL_RESULT:
        history.append(msg)
        state.thinking = None
        state.content = None
        return True

    if msg.role == MessageRole.USER:
        history.append(msg)
        state.thinking = None
        state.content = None
        return True

    if msg.type == MessageType.TEXT:
        appended = False
        if msg.content:
            if state.content is None:
                history.append(msg)
                state.content = msg
                appended = True
            else:
                state.content.content = msg.content
        if msg.usage and state.content:
            state.content.usage = msg.usage
        return appended

    history.append(msg)
    state.thinking = None
    state.content = None
    return True
