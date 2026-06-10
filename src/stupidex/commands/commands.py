from functools import partial
from textual.command import DiscoveryHit, Hit, Hits, Matcher, Provider
from textual.screen import Screen
from textual.widgets import OptionList
from textual.widgets.option_list import Option
from stupidex.llm.models import Model, listModels
from stupidex.llm.session import Session
from stupidex.utils.interface import full_rerender, rerender_footer


class SessionPicker(Screen[str]):
    def __init__(self, sessions: list[Session]) -> None:
        super().__init__()
        self.sessions = sessions

    def compose(self):
        yield OptionList(*[Option(s.name, id=s.id) for s in self.sessions])

    def on_option_list_option_selected(self, event):
        self.dismiss(event.option.id)
        
class ModelPicker(Screen[str]):
    def __init__(self, models: list[Model]) -> None:
        super().__init__()
        self.models = models

    def compose(self):
        yield OptionList(*[Option(m.id, id=m.id) for m in self.models])

    def on_option_list_option_selected(self, event):
        self.dismiss(event.option.id)


class SessionCommands(Provider):
    COMMANDS = {
        "/new": "Start a new session",
        "/switch": "Switch to another session",
        "/delete": "Delete a session",
        "/model": "Change the model for the current session",
    }

    async def discover(self) -> Hits:
        for cmd, desc in self.COMMANDS.items():
            yield DiscoveryHit(cmd, partial(self.run_command, cmd), help=desc)

    async def search(self, query: str) -> Hits:
        matcher = Matcher(query)
        for cmd, desc in self.COMMANDS.items():
            score = matcher.match(cmd)
            if score > 0:
                yield Hit(score, matcher.highlight(cmd), partial(self.run_command, cmd), help=desc)

    async def run_command(self, cmd: str) -> None:
        match cmd:
            case "/new":
                self.app.sessions.create()
                full_rerender(self.app)
            case "/switch":
                sessions = list(self.app.sessions.sessions.values())

                def on_picked(result: str | None):
                    if result:
                        self.app.sessions.switch(result)
                        full_rerender(self.app)

                self.app.push_screen(SessionPicker(sessions), on_picked)
            case "/delete":
                sessions = list(self.app.sessions.sessions.values())

                def on_picked(result: str | None):
                    if result:
                        self.app.sessions.delete(result)
                        if self.app.sessions.active is None:
                            self.app.sessions.create()
                        full_rerender(self.app)

                self.app.push_screen(SessionPicker(sessions), on_picked)
            case "/model":
                models = listModels()

                def on_picked(result: str | None):
                    if result:
                        self.app.sessions.change_model(result)
                        rerender_footer(self.app)   

                self.app.push_screen(ModelPicker(models), on_picked)