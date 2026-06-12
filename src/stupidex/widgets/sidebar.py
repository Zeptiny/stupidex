import os
import time
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Collapsible, Static

from stupidex.agents.manager import SubagentRecord, SubagentState

_TOKEN_THROTTLE_INTERVAL = 0.5


class SidebarSubagentSelected(Message):
    """Emitted when a subagent entry is clicked."""

    def __init__(self, subagent_id: str) -> None:
        self.subagent_id = subagent_id
        super().__init__()


class SidebarMainSelected(Message):
    """Emitted when the Main entry is clicked."""
    pass


class NavEntry(Static):
    """Clickable navigation entry."""

    class Pressed(Message):
        def __init__(self, nav_entry: "NavEntry") -> None:
            self.nav_entry = nav_entry
            super().__init__()

        @property
        def control(self) -> "NavEntry":
            return self.nav_entry

    def __init__(self, label: str, view_id: str, **kwargs) -> None:
        self.view_id = view_id
        super().__init__(label, **kwargs)

    def on_click(self) -> None:
        self.post_message(self.Pressed(self))


class Sidebar(Vertical):
    """Right sidebar showing token counts, subagents, and working directory."""

    DEFAULT_CSS = """
    Sidebar {
        width: 30;
        min-width: 30;
        dock: right;
        background: $surface;
        border-left: tall $primary;
        padding: 1 0 0 0;
    }

    Sidebar #sidebar-tokens-label,
    Sidebar #sidebar-subagents-label {
        color: $text-muted;
        text-style: bold;
        padding: 0 1;
    }

    Sidebar #token-info {
        color: $text;
        padding: 0 1 1 1;
    }

    Sidebar #sidebar-nav {
        height: auto;
        padding: 0 0;
    }

    Sidebar NavEntry {
        width: 100%;
        min-height: 1;
        height: auto;
        padding: 0 1;
        color: $text-muted;
    }

    Sidebar NavEntry:hover {
        background: $surface-darken-1;
    }

    Sidebar NavEntry.-active {
        color: $primary-lighten-1;
        text-style: bold;
    }

    Sidebar #subagent-entries {
        height: auto;
        padding: 0 0;
    }

    Sidebar .subagent-entry {
        width: 100%;
        min-height: 1;
        height: auto;
        padding: 0 1;
        color: $text-muted;
    }

    Sidebar .subagent-entry:hover {
        background: $surface-darken-1;
    }

    Sidebar .subagent-entry.-active {
        color: $primary-lighten-1;
        text-style: bold;
    }

    Sidebar .finished-collapse {
        margin: 0;
        padding: 0 0;
        border: none;
    }

    Sidebar .finished-collapse > CollapsibleTitle {
        color: $text-muted;
        padding: 0 1;
        text-style: dim;
    }

    Sidebar .finished-collapse > CollapsibleTitle:hover {
        background: $surface-darken-1;
    }

    Sidebar .finished-collapse > Contents {
        padding: 0;
    }

    Sidebar #working-directory {
        dock: bottom;
        width: 100%;
        padding: 1;
        color: $text-muted;
        text-style: dim;
    }
    """

    _prompt_tokens: int = 0
    _completion_tokens: int = 0
    _total_tokens: int = 0
    _active_view: str = "main"
    _last_token_update: float = 0
    _token_flush_scheduled: bool = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._usage_by_view: dict = {}
        self._subagent_records: list = []

    def compose(self):
        yield Static("Tokens", id="sidebar-tokens-label")
        yield Static("Context: 0\nResponse: 0\nTotal: 0", id="token-info")
        with Vertical(id="sidebar-nav"):
            yield NavEntry("▸ Main", "main", id="nav-main")
        yield Static("Subagents", id="sidebar-subagents-label")
        yield Vertical(id="subagent-entries")
        yield Static(self._get_working_dir(), id="working-directory")

    def _get_working_dir(self) -> str:
        cwd = os.getcwd()
        if len(cwd) > 26:
            parts = cwd.split("/")
            if len(parts) > 3:
                return f"  ~/{'/'.join(parts[-2:])}"
        return f"  {cwd}"

    def on_nav_entry_pressed(self, event: NavEntry.Pressed) -> None:
        if isinstance(event.control, NavEntry):
            if event.control.view_id == "main":
                self.post_message(SidebarMainSelected())
            else:
                self.post_message(
                    SidebarSubagentSelected(event.control.view_id))

    def set_active(self, view_id: str) -> None:
        self._active_view = view_id
        self._update_active_styles()
        self._show_usage_for_view(view_id)

    def _show_usage_for_view(self, view_id: str) -> None:
        usage = self._usage_by_view.get(view_id)
        if usage:
            self._prompt_tokens, self._completion_tokens, self._total_tokens = usage
        else:
            self._prompt_tokens = 0
            self._completion_tokens = 0
            self._total_tokens = 0
        self._flush_token_update()

    def _update_active_styles(self) -> None:
        try:
            nav = self.query_one("#sidebar-nav")
            for entry in nav.query(NavEntry):
                if entry.view_id == self._active_view:
                    entry.add_class("-active")
                else:
                    entry.remove_class("-active")
        except Exception:
            pass

        try:
            entries = self.query_one("#subagent-entries", Vertical)
            for entry in entries.query(".subagent-entry"):
                if entry.view_id == self._active_view:
                    entry.add_class("-active")
                else:
                    entry.remove_class("-active")
        except Exception:
            pass

    def update_tokens(self, prompt_tokens: int, completion_tokens: int, total_tokens: int, view_id: str = "main") -> None:
        self._usage_by_view[view_id] = (prompt_tokens, completion_tokens, total_tokens)
        if view_id != self._active_view:
            return
        self._prompt_tokens = prompt_tokens
        self._completion_tokens = completion_tokens
        self._total_tokens = total_tokens
        now = time.monotonic()
        if now - self._last_token_update >= _TOKEN_THROTTLE_INTERVAL:
            self._last_token_update = now
            self._flush_token_update()
        elif not self._token_flush_scheduled:
            self._token_flush_scheduled = True
            remaining = _TOKEN_THROTTLE_INTERVAL - (now - self._last_token_update)
            self.set_timer(remaining, self._flush_token_update)

    def _flush_token_update(self) -> None:
        self._token_flush_scheduled = False
        self._last_token_update = time.monotonic()
        try:
            self.query_one("#token-info", Static).update(
                f"Context:  {self._prompt_tokens}\nResponse: {self._completion_tokens}\nTotal:    {self._total_tokens}"
            )
        except Exception:
            pass

    async def update_subagents(self, records: list[SubagentRecord]) -> None:
        self._subagent_records = list(records)
        await self._refresh_subagent_display()

    async def _refresh_subagent_display(self) -> None:
        try:
            container = self.query_one("#subagent-entries", Vertical)
        except Exception:
            return

        records = self._subagent_records
        if not records:
            if container.children:
                await container.remove_children()
            return

        running = [r for r in records if r.state == SubagentState.RUNNING]
        pending = [r for r in records if r.state == SubagentState.PENDING]
        done = [r for r in records if r.state in (
            SubagentState.COMPLETED, SubagentState.FAILED, SubagentState.INTERRUPTED)]

        active_records = list(reversed(running + pending))
        active_ids = [r.id for r in active_records]
        done_ids = [r.id for r in done]

        # Detect current structure
        current_active_ids: list[str] = []
        current_done_ids: list[str] = []
        existing_collapse: Collapsible | None = None
        records_by_id = {r.id: r for r in records}

        for child in container.children:
            if isinstance(child, NavEntry) and child.view_id:
                current_active_ids.append(child.view_id)
            elif isinstance(child, Collapsible):
                existing_collapse = child
                for entry in child.query(NavEntry):
                    if entry.view_id:
                        current_done_ids.append(entry.view_id)

        structure_changed = (active_ids != current_active_ids or
                             done_ids != current_done_ids)

        if not structure_changed:
            # Only labels changed (e.g. elapsed time) — update in-place
            for child in container.children:
                if isinstance(child, NavEntry) and child.view_id:
                    record = records_by_id.get(child.view_id)
                    if record:
                        child.update(self._format_entry(record))
            if existing_collapse:
                for entry in existing_collapse.query(NavEntry):
                    record = records_by_id.get(entry.view_id)
                    if record:
                        entry.update(self._format_entry(record))
            return

        # Structure changed — batch rebuild to avoid flicker
        was_finished_collapsed = True
        if existing_collapse:
            was_finished_collapsed = existing_collapse.collapsed

        # Build active entries synchronously before mounting
        active_entries: list[NavEntry] = []
        for record in active_records:
            label_text = self._format_entry(record)
            entry = NavEntry(label_text, record.id, classes="subagent-entry")
            if record.id == self._active_view:
                entry.add_class("-active")
            active_entries.append(entry)

        # Build done entries synchronously
        done_entries: list[NavEntry] = []
        for record in reversed(done):
            label_text = self._format_entry(record)
            entry = NavEntry(label_text, record.id,
                             classes="subagent-entry")
            if record.id == self._active_view:
                entry.add_class("-active")
            done_entries.append(entry)

        # Single remove, then mount all at once
        await container.remove_children()

        if active_entries:
            await container.mount(*active_entries)

        if done_entries:
            finished_label = f"Finished ({len(done)})"
            collapse = Collapsible(
                classes="finished-collapse",
                title=finished_label,
                collapsed=was_finished_collapsed,
            )
            await container.mount(collapse)
            contents = collapse.query_one("Contents")
            await contents.mount(*done_entries)

    def _format_entry(self, record: SubagentRecord) -> str:
        indicator = self._get_indicator(record.state)
        label = record.label or record.name
        if len(label) > 18:
            label = label[:16] + ".."
        elapsed = self._get_elapsed(record)

        prefix = "▸" if record.id == self._active_view else " "

        color = {
            SubagentState.RUNNING: "green",
            SubagentState.PENDING: "yellow",
            SubagentState.COMPLETED: "dim",
            SubagentState.FAILED: "red",
            SubagentState.INTERRUPTED: "dim red",
        }.get(record.state, "dim")

        text = f"{prefix}{indicator} {label}"
        if elapsed:
            text += f" {elapsed}"
        return f"[{color}]{text}[/{color}]"

    def _get_indicator(self, state: SubagentState) -> str:
        return {
            SubagentState.PENDING: "◌",
            SubagentState.RUNNING: "●",
            SubagentState.COMPLETED: "✓",
            SubagentState.FAILED: "✗",
            SubagentState.INTERRUPTED: "⊘",
        }.get(state, "?")

    def _get_elapsed(self, record: SubagentRecord) -> str | None:
        if record.end_time:
            elapsed = record.end_time - record.start_time
        elif record.start_time:
            elapsed = time.time() - record.start_time
        else:
            return None
        if elapsed < 60:
            return f"{elapsed:.0f}s"
        elif elapsed < 3600:
            return f"{elapsed / 60:.0f}m"
        else:
            return f"{elapsed / 3600:.1f}h"
