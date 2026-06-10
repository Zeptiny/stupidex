from textual.screen import Screen
from textual.widgets import OptionList
from textual.widgets.option_list import Option
from stupidex.domain.session import Session


class SessionPicker(Screen[str]):
    def __init__(self, sessions: list[Session]) -> None:
        super().__init__()
        self.sessions = sessions

    def compose(self):
        yield OptionList(*[Option(s.name, id=s.id) for s in self.sessions])

    def on_option_list_option_selected(self, event):
        self.dismiss(event.option.id)
