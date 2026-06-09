import asyncio
from rich.markdown import Markdown
from textual.app import App, ComposeResult
from textual.events import Resize
from textual.widgets import Input, RichLog
from llm.handle_input import stream_input


class BottomInputApp(App):
    CSS_PATH = "main.tcss"
    messages: list[str] = []
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
        self.messages.append(f"**You:** {user_msg}")
        self._dirty = True
        event.input.clear()
        self.run_worker(self._stream_response(user_msg))

    async def _stream_response(self, user_msg: str) -> None:
        stream = stream_input(user_msg)
        response_so_far = ""

        self.messages.append("")
        llm_index = len(self.messages) - 1

        loop = asyncio.get_event_loop()

        def next_chunk():
            try:
                return next(stream)
            except StopIteration:
                return None

        while True:
            chunk = await loop.run_in_executor(None, next_chunk)
            if chunk is None:
                break
            response_so_far += chunk
            self.messages[llm_index] = f"**LLM:** {response_so_far}"
            self._dirty = True

        # Final render to ensure everything is up to date
        self._dirty = True

    def on_resize(self, event: Resize) -> None:
        self._render_messages()

    def _render_messages(self) -> None:
        output = self.query_one("#output", RichLog)
        output.clear()
        for msg in self.messages:
            output.write(Markdown(msg))
            output.write("")


if __name__ == "__main__":
    app = BottomInputApp()
    app.run()
