import asyncio

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.events import Resize
from textual.reactive import reactive
from textual.widgets import Input, LoadingIndicator, RichLog, Static

from stupidex.commands.session_commands import SessionCommands
from stupidex.domain.message import Message, MessageRole, MessageType
from stupidex.domain.session import SessionManager
from stupidex.llm.client import stream_response
from stupidex.widgets.message_display import render_message


class Stupidex(App):
    CSS_PATH = "main.tcss"
    BINDINGS = [("ctrl+p", "command_palette", "Commands")]
    COMMANDS = {SessionCommands}

    sessions: SessionManager = SessionManager()
    _needs_rerender: reactive[bool] = reactive(False)

    @property
    def messages(self) -> list[Message]:
        return self.sessions.active.messages if self.sessions.active else []

    @property
    def model(self) -> str | None:
        return self.sessions.active.model if self.sessions.active else None

    def compose(self) -> ComposeResult:
        with Horizontal(id="header"):
            yield Static(self.sessions.active.name if self.sessions.active else "No Session", id="title")
        yield RichLog(id="output", wrap=True, highlight=True, markup=True)
        yield Input()
        with Horizontal(id="footer"):
            yield LoadingIndicator(id="spinner")
            yield Static("N/A Model", id="model")
            yield Static("Context: 0 | Response: 0 | Total: 0", id="status")

    def on_mount(self) -> None:
        self.sessions.create()
        self.rerender_all()
        self.query_one(Input).focus()

    def watch__needs_rerender(self, value: bool) -> None:
        if value:
            self._render_messages()
            self.rerender_footer() # TODO: It appears to not make a difference, needs to check if the API only returns usage at the message end
            self._needs_rerender = False

    def on_input_submitted(self, event: Input.Submitted) -> None:
        user_msg = event.value
        event.input.clear()
        self.messages.append(Message(role=MessageRole.USER, content=user_msg))
        self._needs_rerender = True
        self.streaming_started()
        self.run_worker(self._stream_response())

    async def _stream_response(self) -> None:
        stream = stream_response(self.messages, self.model)

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
            elif msg.type == MessageType.TOOL_RESULT:
                self.messages.append(msg)
                thinking_msg = None
                content_msg = None
            else:
                if content_msg is None:
                    self.messages.append(msg)
                    content_msg = msg
                else:
                    content_msg.content = msg.content
                    content_msg.usage = msg.usage

            self._needs_rerender = True

        self._needs_rerender = True
        self.streaming_finished()

    def streaming_started(self) -> None:
        self.query_one("#spinner").display = True

    def streaming_finished(self) -> None:
        self.query_one("#spinner").display = False
        self.rerender_all()

    def on_resize(self, event: Resize) -> None:
        self._render_messages()

    def _render_messages(self) -> None:
        output = self.query_one("#output", RichLog)
        output.clear()
        for msg in self.messages:
            output.write(render_message(msg))

    def rerender_footer(self) -> None:
        if not self.sessions.active:
            return

        last_msg = self.sessions.active.messages[-1] if self.sessions.active.messages else None
        if last_msg and last_msg.usage:
            u = last_msg.usage
            self.query_one("#status", Static).update(
                f"Context: {u.prompt_tokens} | Response: {u.completion_tokens} | Total: {u.total_tokens}"
            )
        else:
            self.query_one("#status", Static).update(
                "Context: 0 | Response: 0 | Total: 0")

        if self.model:
            self.query_one("#model", Static).update(f"{self.model}")
        else:
            self.query_one("#model", Static).update("No Model")

    def rerender_all(self) -> None:
        if not self.sessions.active:
            return

        self.query_one("#title", Static).update(self.sessions.active.name)

        output = self.query_one("#output", RichLog)
        output.clear()
        for msg in self.sessions.active.messages:
            output.write(render_message(msg))

        self.rerender_footer()
