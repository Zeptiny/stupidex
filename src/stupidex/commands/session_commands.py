from functools import partial

from textual.command import DiscoveryHit, Hit, Hits, Matcher, Provider

from stupidex.llm.models import list_models
from stupidex.screens.model_picker import ModelPicker
from stupidex.screens.session_picker import SessionPicker


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
                await self.app.rerender_all()
            case "/switch":
                sessions = list(self.app.sessions.sessions.values())

                async def on_picked(result: str | None):
                    if result:
                        self.app.sessions.switch(result)
                        await self.app.rerender_all()

                self.app.push_screen(SessionPicker(sessions), on_picked)
            case "/delete":
                sessions = list(self.app.sessions.sessions.values())

                async def on_picked(result: str | None):
                    if result:
                        self.app.sessions.delete(result)
                        if self.app.sessions.active is None:
                            self.app.sessions.create()
                        await self.app.rerender_all()

                self.app.push_screen(SessionPicker(sessions), on_picked)
            case "/model":
                models = list_models()

                def on_picked(result: str | None):
                    if result:
                        self.app.sessions.change_model(result)
                        self.app.rerender_footer()

                self.app.push_screen(ModelPicker(models), on_picked)
