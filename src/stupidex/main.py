import asyncio
from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.events import Resize
from textual.widgets import Input, LoadingIndicator, RichLog, Static
from .llm.handle_input import stream_response
from .llm.message import Message, MessageRole, MessageType
from .llm.session import SessionManager
from .commands.commands import SessionCommands
from .utils.interface import full_rerender


class BottomInputApp(App):
    CSS_PATH = "main.tcss"
    BINDINGS = [("ctrl+p", "command_palette", "Commands")]
    COMMANDS = {SessionCommands}
    sessions: SessionManager = SessionManager()
    _dirty: bool = False

    @property
    def messages(self) -> list[Message]:
        return self.sessions.active.messages if self.sessions.active else []

    def compose(self) -> ComposeResult:
        with Horizontal(id="header"):
            yield Static(self.sessions.active.name if self.sessions.active else "No Session", id="title")
        yield RichLog(id="output", wrap=True, highlight=True, markup=True)
        yield Input()
        with Horizontal(id="footer"):
            yield LoadingIndicator(id="spinner")
            yield Static("Context: 0 | Response: 0 | Total: 0", id="status")

    def on_mount(self) -> None:
        self.sessions.create()
        full_rerender(self)
        self.query_one(Input).focus()
        self.set_interval(0.05, self._tick)

    def _tick(self) -> None:
        if self._dirty:
            self._render_messages()
            self._dirty = False

    def on_input_submitted(self, event: Input.Submitted) -> None:
        user_msg = event.value
        event.input.clear()
        self.messages.append(Message(role=MessageRole.USER, content=user_msg))
        self._dirty = True
        self.streaming_started()
        self.run_worker(self._stream_response())

    async def _stream_response(self) -> None:
        stream = stream_response(self.messages)

        thinking_msg = None
        content_msg = None

        loop = asyncio.get_event_loop()

        def next_chunk():
            try:
                return next(stream)
            except StopIteration:
                return None

        while True:
            msg = await loop.run_in_executor(None, next_chunk)
            if msg is None:
                break

            if msg.type == MessageType.THINKING:
                if thinking_msg is None:
                    self.messages.append(msg)
                    thinking_msg = msg
                else:
                    thinking_msg.content = msg.content
            else:
                if content_msg is None:
                    self.messages.append(msg)
                    content_msg = msg
                else:
                    content_msg.content = msg.content
                    content_msg.usage = msg.usage

            self._dirty = True

        self._dirty = True
        self.streaming_finished()

    def streaming_started(self) -> None:
        self.query_one('#spinner').display = True

    def streaming_finished(self) -> None:
        self.query_one('#spinner').display = False
        full_rerender(self)

    def on_resize(self, event: Resize) -> None:
        self._render_messages()

    def _render_messages(self) -> None:
        output = self.query_one("#output", RichLog)
        output.clear()
        for msg in self.messages:
            output.write(msg.render())


def main():
    app = BottomInputApp()
    app.run()


if __name__ == "__main__":
    main()
