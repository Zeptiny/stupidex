import time
from dataclasses import dataclass, field
from typing import Any

from rich.markdown import Markdown
from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Collapsible, Static

from stupidex.domain.message import Message, MessageRole, MessageType
from stupidex.tools import get_tool_registry

_THROTTLE_INTERVAL = 0.2


def get_tool_action_label(tool_name: str) -> str:
    registry = get_tool_registry()
    entry = registry.get(tool_name)
    if entry and entry["tool"].action_label:
        return entry["tool"].action_label
    return f"Using {tool_name}..."


class MessageWidget(Static):
    """Base widget for displaying a chat message."""

    def __init__(self, msg: Message, **kwargs):
        self.msg = msg
        self._last_render_time: float = 0
        self._flush_scheduled: bool = False
        super().__init__(self._build_renderable(), **kwargs)

    def _build_renderable(self):
        raise NotImplementedError

    def update_content(self, content: str) -> None:
        self.msg.content = content
        now = time.monotonic()
        if now - self._last_render_time >= _THROTTLE_INTERVAL:
            self._last_render_time = now
            self.update(self._build_renderable())
        elif not self._flush_scheduled:
            self._flush_scheduled = True
            remaining = _THROTTLE_INTERVAL - (now - self._last_render_time)
            self.set_timer(remaining, self._flush_update)

    def _flush_update(self) -> None:
        self._flush_scheduled = False
        self._last_render_time = time.monotonic()
        self.update(self._build_renderable())


class UserMessageWidget(MessageWidget):
    def _build_renderable(self):
        return Markdown(self.msg.content)


class ThinkingMessageWidget(Static):
    """A collapsible widget that shows 'Thinking...' when collapsed and full thinking when expanded."""

    def __init__(self, msg: Message, **kwargs):
        self.msg = msg
        self._last_render_time: float = 0
        self._flush_scheduled: bool = False
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
            collapsible = self.query_one(Collapsible)
        except Exception:
            return
        if collapsible.collapsed:
            return
        now = time.monotonic()
        if now - self._last_render_time >= _THROTTLE_INTERVAL:
            self._last_render_time = now
            self._do_update()
        elif not self._flush_scheduled:
            self._flush_scheduled = True
            remaining = _THROTTLE_INTERVAL - (now - self._last_render_time)
            self.set_timer(remaining, self._flush_update)

    def _do_update(self) -> None:
        try:
            content_widget = self.query_one(".thinking-content", Static)
            content_widget.update(self.msg.content)
        except Exception:
            pass

    def _flush_update(self) -> None:
        self._flush_scheduled = False
        self._last_render_time = time.monotonic()
        self._do_update()

    def flush(self) -> None:
        """Force immediate update, bypassing throttle."""
        self._flush_scheduled = False
        self._do_update()

    def on_collapsible_toggle(self, event) -> None:
        if not event.collapsed:
            self._do_update()


class AssistantMessageWidget(MessageWidget):
    def _build_renderable(self):
        return Markdown(self.msg.content)


class ErrorMessageWidget(Static):
    """Widget for displaying error messages. Content is never sent to the LLM."""

    DEFAULT_CSS = """
    ErrorMessageWidget {
        background: #3a1010;
        border: wide #dc143c;
        margin: 0 1;
        padding: 0 1;
        height: auto;
    }

    ErrorMessageWidget .error-title {
        text-style: bold;
        color: #ff4444;
    }

    ErrorMessageWidget .error-detail {
        color: #cc8888;
    }
    """

    def __init__(self, msg: Message, **kwargs):
        self.msg = msg
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        title = self.msg.metadata.get("error_title", "Error")
        yield Static(title, classes="error-title")
        yield Static(self.msg.content, classes="error-detail")


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


def create_message_widget(msg: Message) -> Static | None:
    """Factory function to create the appropriate widget for a message."""
    match msg.type:
        case MessageType.THINKING:
            return ThinkingMessageWidget(msg)
        case MessageType.TOOL_CALL:
            return None
        case MessageType.TOOL_RESULT:
            return ToolResultMessageWidget(msg)
        case MessageType.ERROR:
            return ErrorMessageWidget(msg)
        case _:
            if msg.role == MessageRole.USER:
                return UserMessageWidget(msg)
            return AssistantMessageWidget(msg)


@dataclass
class StreamWidgetState:
    """Tracks the current thinking/content/temp widgets for a message stream."""
    thinking: Any = None
    content: Any = None
    temp: list[Static] = field(default_factory=list)


async def mount_streamed_message(container, msg: Message, state: StreamWidgetState) -> None:
    """Mount or update widgets for a streamed message."""
    if msg.type == MessageType.ERROR:
        w = ErrorMessageWidget(msg)
        await container.mount(w)
        w.scroll_visible()
        return
    if msg.type == MessageType.THINKING:
        if state.thinking is None:
            w = ThinkingMessageWidget(msg)
            await container.mount(w)
            state.thinking = w
            w.scroll_visible()
        else:
            state.thinking.update_content(msg.content)
    elif msg.type == MessageType.TOOL_CALL:
        tool_name = msg.metadata.get("tool_name", "")
        temp = Static(get_tool_action_label(tool_name), classes="temp-tool-message")
        await container.mount(temp)
        temp.scroll_visible()
        state.temp.append(temp)
        if state.thinking:
            state.thinking.flush()
        state.content = None
    elif msg.type == MessageType.TOOL_RESULT:
        w = ToolResultMessageWidget(msg)
        if state.temp:
            await container.mount(w, before=state.temp[0])
        else:
            await container.mount(w)
        if state.temp:
            await state.temp.pop(0).remove()
        w.scroll_visible()
        if state.thinking:
            state.thinking.flush()
        state.thinking = None
        state.content = None
    elif msg.role == MessageRole.USER:
        w = UserMessageWidget(msg)
        await container.mount(w)
        w.scroll_visible()
        state.thinking = None
        state.content = None
    else:
        if state.content is None:
            if msg.content:
                if state.thinking:
                    state.thinking.flush()
                w = AssistantMessageWidget(msg)
                await container.mount(w)
                state.content = w
                w.scroll_visible()
        else:
            if msg.content:
                state.content.update_content(msg.content)
