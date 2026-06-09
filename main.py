from textual.app import App, ComposeResult
from textual.widgets import Input, Static
from llm.handle_input import handle_input


class BottomInputApp(App):
    CSS_PATH = "main.tcss"
    
    def compose(self) -> ComposeResult:
        yield Static(id="output")
        yield Input()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        output = self.query_one("#output", Static)
        response = handle_input(event.value)
        output.update(response)
        event.input.clear()


if __name__ == "__main__":
    app = BottomInputApp()
    app.run()
