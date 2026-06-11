import asyncio

from textual.app import App, ComposeResult
from textual.containers import Horizontal, ScrollableContainer
from textual.widgets import Input, LoadingIndicator, Static

from stupidex.commands.session_commands import SessionCommands
from stupidex.domain.message import Message, MessageRole, MessageType
from stupidex.domain.session import SessionManager
from stupidex.llm.client import stream_response
from stupidex.widgets.message_widget import (
    AssistantMessageWidget,
    ThinkingMessageWidget,
    ToolCallMessageWidget,
    ToolResultMessageWidget,
    create_message_widget,
)


class Stupidex(App):
    CSS_PATH = "main.tcss"
    BINDINGS = [("ctrl+p", "command_palette", "Commands")]
    COMMANDS = {SessionCommands}

    sessions: SessionManager = SessionManager()

    @property
    def messages(self) -> list[Message]:
        return self.sessions.active.messages if self.sessions.active else []

    @property
    def model(self) -> str | None:
        return self.sessions.active.model if self.sessions.active else None

    def compose(self) -> ComposeResult:
        with Horizontal(id="header"):
            yield Static(self.sessions.active.name if self.sessions.active else "No Session", id="title")
        yield ScrollableContainer(id="output")
        yield Input()
        with Horizontal(id="footer"):
            yield LoadingIndicator(id="spinner")
            yield Static("N/A Model", id="model")
            yield Static("Context: 0 | Response: 0 | Total: 0", id="status")

    async def on_mount(self) -> None:
        self.sessions.create()
        self.query_one("#title", Static).update(self.sessions.active.name)
        await self.mount_all_messages()
        self.query_one(Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_msg = event.value
        event.input.clear()
        msg = Message(role=MessageRole.USER, content=user_msg)
        self.messages.append(msg)
        await self.mount_message(msg)
        self.streaming_started()
        self.run_worker(self._stream_response())

    async def _stream_response(self) -> None:
        stream = stream_response(self.messages, self.model)
        container = self.query_one("#output", ScrollableContainer)

        thinking_widget: ThinkingMessageWidget | None = None
        content_widget: AssistantMessageWidget | None = None

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
                if thinking_widget is None:
                    self.messages.append(msg)
                    thinking_widget = ThinkingMessageWidget(msg)
                    await container.mount(thinking_widget)
                    thinking_widget.scroll_visible()
                else:
                    thinking_widget.update_content(msg.content)
            elif msg.type == MessageType.TOOL_CALL:
                self.messages.append(msg)
                widget = ToolCallMessageWidget(msg)
                await container.mount(widget)
                widget.scroll_visible()
                thinking_widget = None
                content_widget = None
            elif msg.type == MessageType.TOOL_RESULT:
                self.messages.append(msg)
                widget = ToolResultMessageWidget(msg)
                await container.mount(widget)
                widget.scroll_visible()
                thinking_widget = None
                content_widget = None
            else:
                if content_widget is None:
                    self.messages.append(msg)
                    content_widget = AssistantMessageWidget(msg)
                    await container.mount(content_widget)
                    content_widget.scroll_visible()
                else:
                    content_widget.update_content(msg.content)
                    content_widget.msg.usage = msg.usage

        self.streaming_finished()

    def streaming_started(self) -> None:
        self.query_one("#spinner").display = True

    def streaming_finished(self) -> None:
        self.query_one("#spinner").display = False
        self.rerender_footer()

    async def mount_message(self, msg: Message) -> None:
        container = self.query_one("#output", ScrollableContainer)
        widget = create_message_widget(msg)
        await container.mount(widget)
        widget.scroll_visible()

    async def mount_all_messages(self) -> None:
        container = self.query_one("#output", ScrollableContainer)
        await container.remove_children()
        for msg in self.messages:
            widget = create_message_widget(msg)
            await container.mount(widget)

    async def rerender_all(self) -> None:
        if not self.sessions.active:
            return

        self.query_one("#title", Static).update(self.sessions.active.name)
        await self.mount_all_messages()
        self.rerender_footer()

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
