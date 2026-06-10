from rich.markdown import Markdown
from rich.panel import Panel
from textual.widgets import Static

from stupidex.domain.message import Message, MessageRole, MessageType


class MessageWidget(Static):
    """Base widget for displaying a chat message."""

    def __init__(self, msg: Message, **kwargs):
        self.msg = msg
        super().__init__(self._build_renderable(), **kwargs)

    def _build_renderable(self):
        raise NotImplementedError

    def update_content(self, content: str) -> None:
        self.msg.content = content
        self.update(self._build_renderable())


class UserMessageWidget(MessageWidget):
    def _build_renderable(self):
        return Panel(Markdown(self.msg.content), style="green")


class ThinkingMessageWidget(MessageWidget):
    def _build_renderable(self):
        return Panel(Markdown(f"*{self.msg.content}*"), style="dim")


class AssistantMessageWidget(MessageWidget):
    def _build_renderable(self):
        return Panel(Markdown(self.msg.content))


class ToolCallMessageWidget(MessageWidget):
    def _build_renderable(self):
        tool = self.msg.metadata.get("tool_name", "unknown")
        return Panel(Markdown(f"`{tool}`"), title="Tool Call", style="blue")


class ToolResultMessageWidget(MessageWidget):
    def _build_renderable(self):
        display = self.msg.display if self.msg.display is not None else self.msg.content
        return Panel(display, title="Tool Result", style="blue")


def create_message_widget(msg: Message) -> MessageWidget:
    """Factory function to create the appropriate widget for a message."""
    match msg.type:
        case MessageType.THINKING:
            return ThinkingMessageWidget(msg)
        case MessageType.TOOL_CALL:
            return ToolCallMessageWidget(msg)
        case MessageType.TOOL_RESULT:
            return ToolResultMessageWidget(msg)
        case _:
            if msg.role == MessageRole.USER:
                return UserMessageWidget(msg)
            return AssistantMessageWidget(msg)
