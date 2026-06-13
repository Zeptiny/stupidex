from dataclasses import dataclass

from textual.screen import Screen
from textual.widgets import OptionList
from textual.widgets.option_list import Option


@dataclass
class PickerItem:
    label: str
    id: str


class OptionPicker(Screen[str]):
    """Generic picker screen that displays a list of options and returns the selected id."""

    def __init__(self, items: list[PickerItem]) -> None:
        super().__init__()
        self._items = items

    def compose(self):
        yield OptionList(*[Option(item.label, id=item.id) for item in self._items])

    def on_option_list_option_selected(self, event):
        self.dismiss(event.option.id)
