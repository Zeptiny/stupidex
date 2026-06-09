from rich.markdown import Markdown
from textual.app import App, ComposeResult
from textual.events import Resize
from textual.widgets import Input, RichLog
from llm.handle_input import handle_input


class BottomInputApp(App):
    CSS_PATH = "main.tcss"
    messages: list[str] = []

    def compose(self) -> ComposeResult:
        yield RichLog(id="output", wrap=True, highlight=True, markup=True)
        yield Input()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        user_msg = event.value
        self.messages.append(f"**You:** {user_msg}")
        response = handle_input(user_msg)
        self.messages.append(f"**LLM:** {response}")
        self._render_messages()
        event.input.clear()

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
