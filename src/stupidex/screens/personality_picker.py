from textual.screen import Screen
from textual.widgets import OptionList
from textual.widgets.option_list import Option


class PersonalityPicker(Screen[str]):
    def __init__(self, personalities: list[str], current: str) -> None:
        super().__init__()
        self._personalities = personalities
        self._current = current

    def compose(self):
        yield OptionList(*[
            Option(
                f"● {p}" if p == self._current else f"  {p}",
                id=p,
            )
            for p in self._personalities
        ])

    def on_option_list_option_selected(self, event):
        self.dismiss(event.option.id)
