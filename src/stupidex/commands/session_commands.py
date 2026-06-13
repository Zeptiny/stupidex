from functools import partial

from textual.app import App
from textual.command import DiscoveryHit, Hit, Hits, Matcher, Provider

from stupidex.config import get_current_personality, get_current_theme, set_current_personality, set_current_theme
from stupidex.llm.models import list_models
from stupidex.personality import load_personalities
from stupidex.screens.model_picker import ModelPicker
from stupidex.screens.personality_picker import PersonalityPicker
from stupidex.screens.session_picker import SessionPicker
from stupidex.screens.theme_picker import ThemePicker

COMMANDS = {
    "/new": "Start a new session",
    "/switch": "Switch to another session",
    "/delete": "Delete a session",
    "/model": "Change the model for the current session",
    "/theme": "Switch the application theme",
    "/personality": "Switch the agent personality",
}


async def execute_command(app: App, cmd: str) -> None:
    match cmd:
        case "/new":
            app.sessions.create()
            await app.rerender_all()
        case "/switch":
            sessions = list(app.sessions.sessions.values())

            async def on_picked(result: str | None):
                if result:
                    app.sessions.switch(result)
                    await app.rerender_all()

            app.push_screen(SessionPicker(sessions), on_picked)
        case "/delete":
            sessions = list(app.sessions.sessions.values())

            async def on_picked(result: str | None):
                if result:
                    app.sessions.delete(result)
                    if app.sessions.active is None:
                        app.sessions.create()
                    await app.rerender_all()

            app.push_screen(SessionPicker(sessions), on_picked)
        case "/model":
            models = await list_models()

            async def on_picked(result: str | None):
                if result:
                    app.sessions.change_model(result)
                    await app.rerender_footer()

            app.push_screen(ModelPicker(models), on_picked)
        case "/theme":

            async def on_theme_picked(result: str | None):
                if result:
                    app.switch_theme(result)
                    set_current_theme(result)

            current = get_current_theme()
            app.push_screen(ThemePicker(current), on_theme_picked)
        case "/personality":
            personalities = load_personalities()
            current = get_current_personality()

            async def on_personality_picked(result: str | None):
                if result:
                    set_current_personality(result)

            app.push_screen(PersonalityPicker(list(personalities.keys()), current), on_personality_picked)


class SessionCommands(Provider):
    COMMANDS = COMMANDS

    async def discover(self) -> Hits:
        for cmd, desc in COMMANDS.items():
            yield DiscoveryHit(cmd, partial(self.run_command, cmd), help=desc)

    async def search(self, query: str) -> Hits:
        matcher = Matcher(query)
        for cmd, desc in COMMANDS.items():
            score = matcher.match(cmd)
            if score > 0:
                yield Hit(score, matcher.highlight(cmd), partial(self.run_command, cmd), help=desc)

    async def run_command(self, cmd: str) -> None:
        await execute_command(self.app, cmd)
