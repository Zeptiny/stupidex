import logging
from functools import partial

from textual.app import App
from textual.command import DiscoveryHit, Hit, Hits, Matcher, Provider

from stupidex.config import (
    Config,
    get_config,
    get_current_personality,
    get_current_theme,
    set_current_personality,
    set_current_theme,
)
from stupidex.domain.todo import set_todo_store
from stupidex.llm.providers import resolve_model_metadata
from stupidex.personality import load_personalities
from stupidex.screens.picker import OptionPicker, PickerItem

log = logging.getLogger(__name__)

COMMANDS = {
    "/new": "Start a new session",
    "/switch": "Switch to another session",
    "/delete": "Delete a session",
    "/model": "Change the model for the current session",
    "/theme": "Switch the application theme",
    "/personality": "Switch the agent personality",
    "/index": "Index the project for RAG semantic search",
    "/rag status": "Show RAG index status",
    "/rag clear": "Clear the RAG index",
}


def _token_shorthand(tokens: int) -> str:
    """Render an integer token count as an `Nk` shorthand (128000 -> '128k').

    Values below 1000 are returned as a plain decimal (`500` -> `'500'`) so
    the suffix does not misrepresent the magnitude.
    """
    if tokens >= 1000:
        return f"{tokens // 1000}k"
    return str(tokens)


def _format_model_label(alias: str, model_id: str, metadata: dict) -> str:
    """Render a picker label for a configured model entry.

    Format: `alias/model [vision] [text] {in}k→{out}k` -- each optional
    segment is appended only when its condition holds.

    * `[vision]` -- appended when `metadata["supports_vision"]` is truthy.
    * `[text]` -- appended when `metadata["mode"]` is in `{"chat", "completion"}`.
    * `{in}k→{out}k` -- appended only when BOTH `max_input_tokens` and
      `max_output_tokens` are integers (per U2: `None` means unknown).

    Badges remain plain searchable text since `OptionPicker._filter` matches on
    `label.lower()` (see `screens/picker.py:31-33`).
    """
    parts: list[str] = [f"{alias}/{model_id}"]
    if metadata.get("supports_vision"):
        parts.append("[vision]")
    if metadata.get("mode") in {"chat", "completion"}:
        parts.append("[text]")
    max_in = metadata.get("max_input_tokens")
    max_out = metadata.get("max_output_tokens")
    if isinstance(max_in, int) and isinstance(max_out, int):
        parts.append(f"{_token_shorthand(max_in)}→{_token_shorthand(max_out)}")
    return " ".join(parts)


def _build_model_picker_items(cfg: Config) -> list[PickerItem]:
    """Build the picker-list for `/model` from configured providers + resolved metadata.

    Iterates each configured provider's declared `models` dict (per U1),
    hydrates capability metadata via `resolve_model_metadata` (per U2), and
    builds a `PickerItem` per `(alias, model_id)` pair with the `id` set to
    `f"{alias}/{model_id}"` -- the form `change_model` stores.

    Never raises: malformed provider entries and metadata-resolution failures
    are logged and skipped, keeping the rest of the list intact. The validator
    (U1) should have rejected malformed entries already, so the try/except is
    purely defensive.
    """
    items: list[PickerItem] = []
    for alias, provider_entry in cfg.providers.items():
        if not isinstance(provider_entry, dict):
            log.warning(
                "Skipping provider %r: entry must be a dict, got %s",
                alias,
                type(provider_entry).__name__,
            )
            continue
        models = provider_entry.get("models", {})
        if not isinstance(models, dict):
            log.warning(
                "Skipping provider %r: 'models' must be a dict, got %s",
                alias,
                type(models).__name__,
            )
            continue
        for model_id in models:
            try:
                metadata = resolve_model_metadata(alias, model_id)
                label = _format_model_label(alias, model_id, metadata)
                items.append(PickerItem(label=label, id=f"{alias}/{model_id}"))
            except Exception:  # noqa: BLE001 -- defensive; resolver never raises by design
                log.warning(
                    "Skipping model %r for provider %r: metadata resolution failed",
                    model_id,
                    alias,
                )
                continue
    return items


async def execute_command(app: App, cmd: str) -> None:
    match cmd:
        case "/new":
            app.sessions.create()
            set_todo_store(app.sessions.active.todo_store)
            await app.rerender_all()
        case "/switch":
            sessions = list(app.sessions.sessions.values())
            items = [PickerItem(label=s.name, id=s.id) for s in sessions]

            async def on_picked(result: str | None):
                if result:
                    app.sessions.switch(result)
                    set_todo_store(app.sessions.active.todo_store)
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
                    set_todo_store(app.sessions.active.todo_store)
                    await app.rerender_all()

            app.push_screen(OptionPicker(items), on_picked)
        case "/model":
            cfg = get_config()
            items = _build_model_picker_items(cfg)
            if not items:
                app.notify(
                    "No models configured. Add providers to your config.",
                    severity="warning",
                )
                return

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
        case "/index":
            from stupidex.rag.indexer import index_project

            app.notify("Indexing project for RAG...", severity="information")
            try:
                result = await index_project()
                msg = (
                    f"Indexed {result.files_indexed} files "
                    f"({result.chunks_created} chunks) in {result.duration_seconds:.1f}s. "
                    f"Skipped: {result.files_skipped}, Deleted: {result.files_deleted}"
                )
                if result.errors:
                    msg += f" Errors: {len(result.errors)}"
                app.notify(msg, severity="information" if not result.errors else "warning")
            except Exception as e:
                app.notify(f"Indexing failed: {e}", severity="error")
        case "/rag status":
            from stupidex.rag.indexer import get_status

            status = get_status()
            if status.last_indexed is None and status.total_chunks == 0:
                app.notify("No RAG index exists. Run /index to create one.", severity="information")
            else:
                app.notify(
                    f"RAG: {status.total_files} files, {status.total_chunks} chunks, "
                    f"indexed: {status.last_indexed or 'never'}",
                    severity="information",
                )
        case "/rag clear":
            from stupidex.rag.indexer import clear_index

            clear_index()
            app.notify("RAG index cleared.", severity="information")


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
