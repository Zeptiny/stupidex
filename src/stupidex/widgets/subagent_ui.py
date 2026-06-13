from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual.containers import ScrollableContainer
from textual.timer import Timer
from textual.widgets import Static, TabbedContent, TabPane

from stupidex.agents.manager import SubagentRecord, SubagentState
from stupidex.domain.message import Message, MessageRole, MessageType
from stupidex.widgets.message_widget import (
    AssistantMessageWidget,
    ThinkingMessageWidget,
    ToolResultMessageWidget,
    UserMessageWidget,
    get_tool_action_label,
)
from stupidex.widgets.sidebar import Sidebar

if TYPE_CHECKING:
    from textual.app import App


class SubagentUIManager:
    """Manages subagent tabs, widgets, and sidebar updates."""

    def __init__(self, app: App) -> None:
        self.app = app
        self._widgets: dict[str, dict[str, Any]] = {}
        self._timer: Timer | None = None

    def setup(self, manager) -> None:
        """Wire callbacks on the subagent manager."""
        manager.on_spawn = self.on_spawn
        self._set_manager(manager)

    def _set_manager(self, manager) -> None:
        from stupidex.agents.manager import set_subagent_manager
        set_subagent_manager(manager)

    def has_running(self, manager) -> bool:
        terminal = {SubagentState.COMPLETED, SubagentState.FAILED, SubagentState.INTERRUPTED}
        return any(r.state not in terminal for r in manager.all_records())

    async def on_spawn(self, record: SubagentRecord) -> None:
        record.on_message = lambda msg, rid=record.id: self.on_message(rid, msg)
        record.on_state_change = lambda state, rid=record.id: self.on_state_change(rid, state)
        tabs = self.app.query_one("#tabs", TabbedContent)
        pane = TabPane(self._tab_label(record), id=f"sub-{record.id}")
        await tabs.add_pane(pane)
        for msg in record.messages[record.messages_mounted :]:
            await self.on_message(record.id, msg)
        await self.update_sidebar()

    async def on_message(self, subagent_id: str, msg: Message) -> None:
        if msg.usage:
            try:
                sidebar = self.app.query_one("#sidebar", Sidebar)
                sidebar.update_tokens(
                    msg.usage.prompt_tokens, msg.usage.completion_tokens, msg.usage.total_tokens, view_id=subagent_id
                )
            except Exception:
                pass

        try:
            pane = self.app.query_one(f"#sub-{subagent_id}", TabPane)
        except Exception:
            return
        try:
            container = pane.query_one(ScrollableContainer)
        except Exception:
            container = ScrollableContainer()
            await pane.mount(container)

        widgets = self._widgets.setdefault(subagent_id, {"temp": []})
        thinking_widget = widgets.get("thinking")
        content_widget = widgets.get("content")
        temp_widgets: list[Static] = widgets.get("temp", [])
        if isinstance(temp_widgets, list) is False:
            temp_widgets = []
            widgets["temp"] = temp_widgets

        if msg.type == MessageType.THINKING:
            if thinking_widget is None:
                w = ThinkingMessageWidget(msg)
                await container.mount(w)
                widgets["thinking"] = w
                w.scroll_visible()
            else:
                thinking_widget.update_content(msg.content)
        elif msg.type == MessageType.TOOL_CALL:
            tool_name = msg.metadata.get("tool_name", "")
            temp = Static(get_tool_action_label(tool_name), classes="temp-tool-message")
            await container.mount(temp)
            temp.scroll_visible()
            temp_widgets.append(temp)
            widgets["thinking"] = None
            widgets["content"] = None
        elif msg.type == MessageType.TOOL_RESULT:
            if temp_widgets:
                await temp_widgets.pop(0).remove()
            w = ToolResultMessageWidget(msg)
            await container.mount(w)
            w.scroll_visible()
            widgets["thinking"] = None
            widgets["content"] = None
        elif msg.role == MessageRole.USER:
            w = UserMessageWidget(msg)
            await container.mount(w)
            w.scroll_visible()
            widgets["thinking"] = None
            widgets["content"] = None
        else:
            if content_widget is None:
                if msg.content:
                    w = AssistantMessageWidget(msg)
                    await container.mount(w)
                    widgets["content"] = w
                    w.scroll_visible()
            else:
                if msg.content:
                    content_widget.update_content(msg.content)

    async def on_state_change(self, subagent_id: str, state: SubagentState) -> None:
        try:
            tabs = self.app.query_one("#tabs", TabbedContent)
            tab = tabs.get_tab(f"sub-{subagent_id}")
        except Exception:
            return
        manager = self.app.sessions.active.subagent_manager if self.app.sessions.active else None
        if not manager:
            return
        record = manager.get_record(subagent_id)
        if not record:
            return
        tab.update(self._tab_label(record))
        await self.update_sidebar()

    async def sync_tabs(self, manager) -> None:
        tabs = self.app.query_one("#tabs", TabbedContent)
        pane_ids = [p.id for p in tabs.query("TabPane") if p.id and p.id.startswith("sub-")]
        for pane_id in pane_ids:
            await tabs.remove_pane(pane_id)
        self._widgets.clear()
        manager.on_spawn = self.on_spawn
        self._set_manager(manager)
        for record in manager.all_records():
            pane = TabPane(self._tab_label(record), id=f"sub-{record.id}")
            await tabs.add_pane(pane)
            record.on_message = lambda msg, rid=record.id: self.on_message(rid, msg)
            record.on_state_change = lambda state, rid=record.id: self.on_state_change(rid, state)
            for msg in record.messages:
                await self.on_message(record.id, msg)

    async def update_sidebar(self) -> None:
        try:
            sidebar = self.app.query_one("#sidebar", Sidebar)
        except Exception:
            return
        if self.app.sessions.active:
            records = self.app.sessions.active.subagent_manager.all_records()
            await sidebar.update_subagents(records)
        else:
            await sidebar.update_subagents([])
        self._manage_timer()

    def _manage_timer(self) -> None:
        manager = self.app.sessions.active.subagent_manager if self.app.sessions.active else None
        has_running = manager is not None and self.has_running(manager)
        if has_running and self._timer is None:
            self._timer = self.app.set_interval(1.0, self._tick_timer)
        elif not has_running and self._timer is not None:
            self._timer.stop()
            self._timer = None

    async def _tick_timer(self) -> None:
        await self.update_sidebar()

    @staticmethod
    def _tab_label(record: SubagentRecord) -> str:
        from stupidex.agents.manager import SUBAGENT_INDICATORS
        indicator = SUBAGENT_INDICATORS.get(record.state, "?")
        return f"{indicator} {record.label}"
