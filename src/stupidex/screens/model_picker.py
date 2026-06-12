from textual.screen import Screen
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from stupidex.llm.models import Model


class ModelPicker(Screen[str]):
    def __init__(self, models: list[Model]) -> None:
        super().__init__()
        self.models = models

    def compose(self):
        yield OptionList(*[Option(m.id, id=m.id) for m in self.models])

    def on_option_list_option_selected(self, event):
        self.dismiss(event.option.id)
