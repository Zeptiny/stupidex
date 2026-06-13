from textual.screen import Screen
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from stupidex.themes import get_theme_registry


class ThemePicker(Screen[str]):
    def __init__(self, current: str = "") -> None:
        super().__init__()
        self._registry = get_theme_registry()
        self._current = current

    def compose(self):
        yield OptionList(*[
            Option(
                f"● {name}" if name == self._current else f"  {name}",
                id=name,
            )
            for name in self._registry.list_themes()
        ])

    def on_option_list_option_selected(self, event):
        self.dismiss(event.option.id)
