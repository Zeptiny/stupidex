from functools import partial

from textual.app import App
from textual.command import DiscoveryHit, Hit, Hits, Matcher, Provider

from stupidex.config import get_current_personality, get_current_theme, set_current_personality, set_current_theme
from stupidex.llm.models import list_models
from stupidex.personality import load_personalities
from stupidex.screens.picker import OptionPicker, PickerItem

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
            items = [PickerItem(label=s.name, id=s.id) for s in sessions]

            async def on_picked(result: str | None):
                if result:
                    app.sessions.switch(result)
                    await app.rerender_all()

            app.push_screen(OptionPicker(items), on_picked)
        case "/delete":
            sessions = list(app.sessions.sessions.values())
            items = [PickerItem(label=s.name, id=s.id) for s in sessions]

            async def on_picked(result: str | None):
                if result:
                    app.sessions.delete(result)
                    if app.sessions.active is None:
                        app.sessions.create()
                    await app.rerender_all()

            app.push_screen(OptionPicker(items), on_picked)
        case "/model":
            models = await list_models()
            if not models:
                app.notify("Failed to fetch models", severity="error")
                return
            items = [PickerItem(label=m.id, id=m.id) for m in models]

            async def on_picked(result: str | None):
                if result:
                    app.sessions.change_model(result)
                    await app.rerender_footer()

            app.push_screen(OptionPicker(items), on_picked)
        case "/theme":
            from stupidex.themes import get_theme_registry
            registry = get_theme_registry()
            current = get_current_theme()
            items = [
                PickerItem(label=f"● {name}" if name == current else f"  {name}", id=name)
                for name in registry.list_themes()
            ]

            async def on_theme_picked(result: str | None):
                if result:
                    app.switch_theme(result)
                    set_current_theme(result)

            app.push_screen(OptionPicker(items), on_theme_picked)
        case "/personality":
            personalities = load_personalities()
            current = get_current_personality()
            items = [
                PickerItem(label=f"● {p}" if p == current else f"  {p}", id=p)
                for p in personalities
            ]

            async def on_personality_picked(result: str | None):
                if result:
                    set_current_personality(result)

            app.push_screen(OptionPicker(items), on_personality_picked)


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
