from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Collapsible, Static

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


class ThinkingMessageWidget(Static):
    """A collapsible widget that shows 'Thinking...' when collapsed and full thinking when expanded."""

    def __init__(self, msg: Message, **kwargs):
        self.msg = msg
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Collapsible(
            Static(self.msg.content, classes="thinking-content"),
            title="Thinking...",
            collapsed=True,
            classes="thinking-collapse",
        )

    def update_content(self, content: str) -> None:
        self.msg.content = content
        try:
            content_widget = self.query_one(".thinking-content", Static)
            content_widget.update(self.msg.content)
        except Exception:
            pass


class AssistantMessageWidget(MessageWidget):
    def _build_renderable(self):
        return Panel(Markdown(self.msg.content))


class ToolCallMessageWidget(MessageWidget):
    def _build_renderable(self):
        tool = self.msg.metadata.get("tool_name", "unknown")
        return Panel(Markdown(f"`{tool}`"), title="Tool Call", style="blue")


class ToolResultMessageWidget(Static):
    """A collapsible widget that shows the display summary when collapsed and full content when expanded."""

    def __init__(self, msg: Message, **kwargs):
        self.msg = msg
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        display = self.msg.display if self.msg.display is not None else self.msg.content
        yield Collapsible(
            Static(Text(self.msg.content), classes="tool-result-content"),
            title=display,
            collapsed=True,
            classes="tool-result-collapse",
        )


def create_message_widget(msg: Message) -> Static:
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
