import re
import time
from dataclasses import dataclass, field
from typing import Any

from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import Collapsible, Static

from stupidex.domain.message import Message, MessageRole, MessageType
from stupidex.tools import get_tool_registry

_THROTTLE_INTERVAL = 0.2
_TOOL_RESULT_FALLBACK_TITLE = "Tool result"
_TOOL_RESULT_TITLE_MAX_LENGTH = 120
_EDIT_DIFF_MARKER = "\n\nDiff:\n"
_EDIT_DIFF_CDATA_RE = re.compile(
    r'<diff\s+format="unified">\s*<!\[CDATA\[\n?(?P<diff>.*?)\n?\]\]>\s*</diff>',
    re.DOTALL,
)
_DIFF_HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,\d+)? \+(?P<new_start>\d+)(?:,\d+)? @@"
)
_DIFF_LINE_NUMBER_WIDTH = 4
_DIFF_CONTEXT_STYLE = "#c9d1d9"
_DIFF_ADDED_STYLE = "#d7ffdf on #153b25"
_DIFF_REMOVED_STYLE = "#ffd7d7 on #3b1717"
_DIFF_META_STYLE = "#7d8590"
_DIFF_SYNTAX_THEME = "ansi_dark"
_DIFF_LEXER_BY_EXTENSION = {
    ".bash": "bash",
    ".css": "css",
    ".go": "go",
    ".html": "html",
    ".java": "java",
    ".js": "javascript",
    ".json": "json",
    ".jsx": "jsx",
    ".md": "markdown",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".sh": "bash",
    ".tcss": "css",
    ".toml": "toml",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".yaml": "yaml",
    ".yml": "yaml",
}


def get_tool_action_label(tool_name: str) -> str:
    registry = get_tool_registry()
    entry = registry.get(tool_name)
    if entry and entry["tool"].action_label:
        return entry["tool"].action_label
    return f"Using {tool_name}..."


def get_tool_result_title(msg: Message) -> str:
    if msg.display is None:
        return _TOOL_RESULT_FALLBACK_TITLE

    title = " ".join(msg.display.split())
    if not title:
        return _TOOL_RESULT_FALLBACK_TITLE
    if len(title) <= _TOOL_RESULT_TITLE_MAX_LENGTH:
        return title
    return title[: _TOOL_RESULT_TITLE_MAX_LENGTH - 3].rstrip() + "..."


def get_tool_result_renderable(msg: Message) -> Text:
    edit_diff = _extract_edit_diff(msg)
    if edit_diff is not None:
        return _render_unified_diff(edit_diff)
    return Text(msg.content)


def _extract_edit_diff(msg: Message) -> str | None:
    if msg.display is None or not msg.display.startswith("Edited "):
        return None
    cdata_match = _EDIT_DIFF_CDATA_RE.search(msg.content)
    if cdata_match:
        diff_text = cdata_match.group("diff").replace("]]]]><![CDATA[>", "]]>").rstrip("\n")
        return diff_text or None

    if _EDIT_DIFF_MARKER not in msg.content:
        return None

    diff_text = msg.content.split(_EDIT_DIFF_MARKER, 1)[1].rstrip("\n")
    return diff_text or None


def _render_unified_diff(diff_text: str) -> Text:
    rendered = Text(no_wrap=True, overflow="crop")
    lexer = _guess_diff_lexer(diff_text)
    old_line = 0
    new_line = 0
    hunk_count = 0

    for raw_line in diff_text.splitlines():
        hunk_match = _DIFF_HUNK_RE.match(raw_line)
        if hunk_match:
            if hunk_count:
                rendered.append(f"{':':>{_DIFF_LINE_NUMBER_WIDTH}}\n", style=_DIFF_META_STYLE)
            hunk_count += 1
            old_line = int(hunk_match.group("old_start"))
            new_line = int(hunk_match.group("new_start"))
            continue

        if not raw_line or raw_line.startswith(("---", "+++")):
            continue

        if raw_line.startswith("+"):
            _append_diff_line(rendered, new_line, "+", raw_line[1:], _DIFF_ADDED_STYLE, lexer)
            new_line += 1
        elif raw_line.startswith("-"):
            _append_diff_line(rendered, old_line, "-", raw_line[1:], _DIFF_REMOVED_STYLE, lexer)
            old_line += 1
        elif raw_line.startswith(" "):
            _append_diff_line(rendered, new_line, " ", raw_line[1:], _DIFF_CONTEXT_STYLE, lexer)
            old_line += 1
            new_line += 1
        else:
            rendered.append(f"{'':>{_DIFF_LINE_NUMBER_WIDTH}}  {raw_line}\n", style=_DIFF_META_STYLE)

    if rendered.plain:
        return rendered
    return Text(diff_text, no_wrap=True, overflow="crop")


def _guess_diff_lexer(diff_text: str) -> str:
    path = _extract_diff_path(diff_text)
    code = "\n".join(
        line[1:]
        for line in diff_text.splitlines()
        if line.startswith((" ", "+", "-")) and not line.startswith(("+++", "---"))
    )
    if path is None:
        return "default"

    for suffix, lexer in _DIFF_LEXER_BY_EXTENSION.items():
        if path.endswith(suffix):
            return lexer

    try:
        return Syntax.guess_lexer(path, code=code)
    except Exception:
        return "default"


def _extract_diff_path(diff_text: str) -> str | None:
    for line in diff_text.splitlines():
        if line.startswith("+++ new/"):
            return line.removeprefix("+++ new/")
    return None


def _append_diff_line(
    rendered: Text,
    line_number: int,
    prefix: str,
    content: str,
    style: str,
    lexer: str,
) -> None:
    rendered.append(f"{line_number:>{_DIFF_LINE_NUMBER_WIDTH}} {prefix}", style=style)
    rendered.append_text(_highlight_diff_content(content, style, lexer))
    rendered.append("\n", style=style)


def _highlight_diff_content(content: str, style: str, lexer: str) -> Text:
    highlighted = Syntax(content, lexer, theme=_DIFF_SYNTAX_THEME).highlight(content)
    code = Text(content, style=style)
    for span in highlighted.spans:
        if span.start >= len(content):
            continue
        code.stylize(span.style, span.start, min(span.end, len(content)))
    return code


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
        yield Collapsible(
            Static(get_tool_result_renderable(self.msg), classes="tool-result-content"),
            title=get_tool_result_title(self.msg),
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
        w = ToolResultMessageWidget(msg, classes="after-thinking" if state.thinking else None)
        if state.temp:
            temp = state.temp.pop(0)
            async with container.batch():
                await container.mount(w, before=temp)
                await temp.remove()
        else:
            await container.mount(w)
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
                state.thinking = None
                w.scroll_visible()
        else:
            if msg.content:
                state.content.update_content(msg.content)
