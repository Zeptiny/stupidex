from rich.markdown import Markdown
from rich.panel import Panel

from stupidex.domain.message import Message, MessageRole, MessageType


def render_message(msg: Message) -> Panel | Markdown:
    display = msg.display if msg.display is not None else msg.content
    match msg.type:
        case MessageType.THINKING:
            return Panel(Markdown(f"*{msg.content}*"), style="dim")
        case MessageType.TOOL_CALL:
            tool = msg.metadata.get("tool_name", "unknown")
            return Panel(Markdown(f"`{tool}`"), title="Tool Call", style="blue")
        case MessageType.TOOL_RESULT:
            return Panel(display, title="Tool Result", style="blue")
        case _:
            if msg.role == MessageRole.USER:
                return Panel(Markdown(msg.content), style="green")
            return Panel(Markdown(msg.content))
