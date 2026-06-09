import asyncio
from textual.app import App, ComposeResult
from textual.events import Resize
from textual.widgets import Input, RichLog
from .llm.handle_input import stream_input
from .llm.message import Message, MessageRole, MessageType


class BottomInputApp(App):
    CSS_PATH = "main.tcss"
    messages: list[Message] = []
    _dirty: bool = False

    def compose(self) -> ComposeResult:
        yield RichLog(id="output", wrap=True, highlight=True, markup=True)
        yield Input()

    def on_mount(self) -> None:
        self.set_interval(0.05, self._tick)

    def _tick(self) -> None:
        if self._dirty:
            self._render_messages()
            self._dirty = False

    def on_input_submitted(self, event: Input.Submitted) -> None:
        user_msg = event.value
        self.messages.append(Message(role=MessageRole.USER, content=user_msg))
        self._dirty = True
        event.input.clear()
        self.run_worker(self._stream_response(user_msg))

    async def _stream_response(self, user_msg: str) -> None:
        stream = stream_input(user_msg)

        thinking_idx = None
        content_idx = None

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
                if thinking_idx is None:
                    self.messages.append(msg)
                    thinking_idx = len(self.messages) - 1
                else:
                    self.messages[thinking_idx] = msg
            else:
                if content_idx is None:
                    self.messages.append(msg)
                    content_idx = len(self.messages) - 1
                else:
                    self.messages[content_idx] = msg

            self._dirty = True

        # Final render to ensure everything is up to date
        self._dirty = True

    def on_resize(self, event: Resize) -> None:
        self._render_messages()

    def _render_messages(self) -> None:
        output = self.query_one("#output", RichLog)
        output.clear()
        for msg in self.messages:
            output.write(msg.render())
            output.write("")


def main():
    app = BottomInputApp()
    app.run()


if __name__ == "__main__":
    main()
