import asyncio
from enum import Enum

from textual.app import App, ComposeResult
from textual.containers import Horizontal, ScrollableContainer
from textual.timer import Timer
from textual.widgets import LoadingIndicator, Static, TabbedContent, TabPane, TextArea

from stupidex.agents import get_agent_registry
from stupidex.agents.manager import SubagentRecord, SubagentState, set_subagent_manager
from stupidex.commands.session_commands import SessionCommands
from stupidex.domain.message import Message, MessageRole, MessageType
from stupidex.domain.session import SessionManager
from stupidex.llm.client import stream_response
from stupidex.widgets.message_widget import (
    AssistantMessageWidget,
    ThinkingMessageWidget,
    ToolResultMessageWidget,
    UserMessageWidget,
    create_message_widget,
    get_tool_action_label,
)
from stupidex.widgets.sidebar import Sidebar, SidebarMainSelected, SidebarSubagentSelected


class InterruptState(Enum):
    IDLE = "idle"
    CONFIRM_AGENT = "confirm_agent"
    CONFIRM_SUBAGENTS = "confirm_subagents"


class Stupidex(App):
    CSS_PATH = "main.tcss"
    BINDINGS = [
        ("ctrl+p", "command_palette", "Commands"),
        ("escape", "interrupt", "Interrupt"),
        ("ctrl+s", "submit_input", "Submit"),
        ("ctrl+c", "clear_input", "Clear Input"),
    ]
    COMMANDS = {SessionCommands}

    sessions: SessionManager = SessionManager()
    _interrupt_state: InterruptState = InterruptState.IDLE
    _active_worker: object | None = None  # Textual Worker
    _subagent_timer: Timer | None = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._subagent_widgets: dict[str, dict[str,
                                               ThinkingMessageWidget | AssistantMessageWidget | Static | None]] = {}

    @property
    def messages(self) -> list[Message]:
        return self.sessions.active.messages if self.sessions.active else []

    @property
    def model(self) -> str | None:
        return self.sessions.active.model if self.sessions.active else None

    def compose(self) -> ComposeResult:
        with Horizontal(id="header"):
            yield Static(self.sessions.active.name if self.sessions.active else "No Session", id="title")
        with TabbedContent(id="tabs", initial="main"), TabPane("Main", id="main"):
            yield ScrollableContainer(id="output")
        yield TextArea(id="input")
        with Horizontal(id="footer"):
            yield LoadingIndicator(id="spinner")
            yield Static("N/A Model", id="model")
            yield Static("", id="interrupt-hint")
        yield Sidebar(id="sidebar")

    async def on_mount(self) -> None:
        self.sessions.create()
        self.query_one("#title", Static).update(self.sessions.active.name)
        await self.mount_all_messages()
        self.query_one("#input", TextArea).display = True
        self.query_one("#input", TextArea).focus()
        try:
            sidebar = self.query_one("#sidebar", Sidebar)
            sidebar.set_active("main")
        except Exception:
            pass
        await self.rerender_footer()

    def _is_streaming(self) -> bool:
        return self._active_worker is not None and not self._active_worker.is_finished

    def _has_running_subagents(self) -> bool:
        if not self.sessions.active:
            return False
        terminal = {SubagentState.COMPLETED,
                    SubagentState.FAILED, SubagentState.INTERRUPTED}
        return any(
            r.state not in terminal
            for r in self.sessions.active.subagent_manager._subagents.values()
        )

    async def action_interrupt(self) -> None:
        hint = self.query_one("#interrupt-hint", Static)

        if self._interrupt_state == InterruptState.IDLE:
            if self._is_streaming():
                self._interrupt_state = InterruptState.CONFIRM_AGENT
                hint.update(
                    "[bold yellow]Press Esc again to interrupt agent[/]")
            elif self._has_running_subagents():
                self._interrupt_state = InterruptState.CONFIRM_SUBAGENTS
                hint.update(
                    "[bold red]Press Esc again to interrupt subagents[/]")
        elif self._interrupt_state == InterruptState.CONFIRM_AGENT:
            self._interrupt_state = InterruptState.CONFIRM_SUBAGENTS
            if self._active_worker and not self._active_worker.is_finished:
                self._active_worker.cancel()
            if self._has_running_subagents():
                hint.update(
                    "[bold red]Press Esc again to interrupt subagents[/]")
            else:
                self._interrupt_state = InterruptState.IDLE
                hint.update("")
        elif self._interrupt_state == InterruptState.CONFIRM_SUBAGENTS:
            if self.sessions.active:
                cancelled = self.sessions.active.subagent_manager.cancel_running()
                if cancelled:
                    names = []
                    for sid in cancelled:
                        record = self.sessions.active.subagent_manager.get_record(
                            sid)
                        if record:
                            names.append(record.label or record.name)
                    detail = ", ".join(
                        names) if names else f"{len(cancelled)} subagent(s)"
                    interrupt_msg = Message(
                        role=MessageRole.ASSISTANT,
                        content=f"[Subagents interrupted by user: {detail}]",
                    )
                    self.messages.append(interrupt_msg)
                    try:
                        await self.mount_message(interrupt_msg)
                    except Exception:
                        pass
            self._interrupt_state = InterruptState.IDLE
            hint.update("")

    def _reset_interrupt_state(self) -> None:
        self._interrupt_state = InterruptState.IDLE
        try:
            self.query_one("#interrupt-hint", Static).update("")
        except Exception:
            pass

    async def action_submit_input(self) -> None:
        if self._is_streaming():
            return
        text_area = self.query_one("#input", TextArea)
        user_msg = text_area.text.strip()
        if not user_msg:
            return
        text_area.clear()
        msg = Message(role=MessageRole.USER, content=user_msg)
        self.messages.append(msg)
        await self.mount_message(msg)
        self._reset_interrupt_state()
        self.streaming_started()
        self._active_worker = self.run_worker(
            self._stream_response(), exit_on_error=False)

    async def on_submittextarea_submitted(self, event: TextArea.Submitted) -> None:
        await self.action_submit_input()

    def action_clear_input(self) -> None:
        self.query_one("#input", TextArea).clear()

    async def _stream_response(self) -> None:
        container = self.query_one("#output", ScrollableContainer)

        thinking_widget: ThinkingMessageWidget | None = None
        content_widget: AssistantMessageWidget | None = None
        temp_widgets: list[Static] = []

        set_subagent_manager(self.sessions.active.subagent_manager)
        self.sessions.active.subagent_manager.on_spawn = self._on_subagent_spawned

        try:
            general = get_agent_registry()["general"]
            async for msg in stream_response(
                messages=self.messages,
                model=self.model,
                available_tools=general.available_tools,
                system_prompt=general.system_prompt,
            ):

                if msg.type == MessageType.THINKING:
                    if thinking_widget is None:
                        self.messages.append(msg)
                        thinking_widget = ThinkingMessageWidget(msg)
                        await container.mount(thinking_widget)
                        thinking_widget.scroll_visible()
                    else:
                        thinking_widget.update_content(msg.content)
                elif msg.type == MessageType.TOOL_CALL:
                    self.messages.append(msg)
                    tool_name = msg.metadata.get("tool_name", "")
                    temp = Static(get_tool_action_label(tool_name), classes="temp-tool-message")
                    await container.mount(temp)
                    temp.scroll_visible()
                    temp_widgets.append(temp)
                    thinking_widget = None
                    content_widget = None
                elif msg.type == MessageType.TOOL_RESULT:
                    self.messages.append(msg)
                    if temp_widgets:
                        await temp_widgets.pop(0).remove()
                    widget = ToolResultMessageWidget(msg)
                    await container.mount(widget)
                    widget.scroll_visible()
                    thinking_widget = None
                    content_widget = None
                else:
                    if content_widget is None:
                        if msg.content:
                            self.messages.append(msg)
                            content_widget = AssistantMessageWidget(msg)
                            await container.mount(content_widget)
                            content_widget.scroll_visible()
                        elif msg.usage:
                            self.messages.append(msg)
                    else:
                        if msg.content:
                            content_widget.update_content(msg.content)
                        if msg.usage:
                            content_widget.msg.usage = msg.usage
                    if msg.usage:
                        await self.rerender_footer()
        except asyncio.CancelledError:
            for tw in temp_widgets:
                try:
                    await tw.remove()
                except Exception:
                    pass
            temp_widgets.clear()
            interrupted_msg = Message(
                role=MessageRole.ASSISTANT,
                content="[Interrupted by user]",
            )
            self.messages.append(interrupted_msg)
            try:
                await self.mount_message(interrupted_msg)
            except Exception:
                pass
            raise
        finally:
            await self.streaming_finished()

    def streaming_started(self) -> None:
        self.query_one("#spinner").display = True

    async def streaming_finished(self) -> None:
        self.query_one("#spinner").display = False
        if self._interrupt_state != InterruptState.CONFIRM_SUBAGENTS:
            self._reset_interrupt_state()
        await self.rerender_footer()

    async def _on_subagent_spawned(self, record: SubagentRecord) -> None:
        record.on_message = lambda msg, rid=record.id: self._on_subagent_message(
            rid, msg)
        record.on_state_change = lambda state, rid=record.id: self._on_subagent_state_change(
            rid, state)
        tabs = self.query_one("#tabs", TabbedContent)
        pane = TabPane(self._tab_label(record), id=f"sub-{record.id}")
        await tabs.add_pane(pane)
        for msg in record.messages[record.messages_mounted:]:
            await self._on_subagent_message(record.id, msg)
        await self._update_sidebar_subagents()

    async def _on_subagent_message(self, subagent_id: str, msg: Message) -> None:
        if msg.usage:
            try:
                sidebar = self.query_one("#sidebar", Sidebar)
                sidebar.update_tokens(msg.usage.prompt_tokens, msg.usage.completion_tokens, msg.usage.total_tokens, view_id=subagent_id)
            except Exception:
                pass

        try:
            pane = self.query_one(f"#sub-{subagent_id}", TabPane)
        except Exception:
            return
        try:
            container = pane.query_one(ScrollableContainer)
        except Exception:
            container = ScrollableContainer()
            await pane.mount(container)

        widgets = self._subagent_widgets.setdefault(subagent_id, {"temp": []})
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

    async def _on_subagent_state_change(self, subagent_id: str, state: SubagentState) -> None:
        try:
            tabs = self.query_one("#tabs", TabbedContent)
            tab = tabs.get_tab(f"sub-{subagent_id}")
        except Exception:
            return
        record = self.sessions.active.subagent_manager.get_record(subagent_id)
        if not record:
            return
        tab.update(self._tab_label(record))
        await self._update_sidebar_subagents()

    def on_sidebar_main_selected(self, event: SidebarMainSelected) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = "main"
        self.query_one("#input", TextArea).display = True
        sidebar = self.query_one("#sidebar", Sidebar)
        sidebar.set_active("main")

    def on_sidebar_subagent_selected(self, event: SidebarSubagentSelected) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = f"sub-{event.subagent_id}"
        self.query_one("#input", TextArea).display = False
        sidebar = self.query_one("#sidebar", Sidebar)
        sidebar.set_active(event.subagent_id)

    async def mount_message(self, msg: Message) -> None:
        container = self.query_one("#output", ScrollableContainer)
        widget = create_message_widget(msg)
        if widget is None:
            return
        await container.mount(widget)
        widget.scroll_visible()

    async def mount_all_messages(self) -> None:
        container = self.query_one("#output", ScrollableContainer)
        await container.remove_children()
        for msg in self.messages:
            widget = create_message_widget(msg)
            if widget is not None:
                await container.mount(widget)

    async def rerender_all(self) -> None:
        if not self.sessions.active:
            return

        self.query_one("#title", Static).update(self.sessions.active.name)
        await self.mount_all_messages()
        await self._sync_subagent_tabs()
        await self.rerender_footer()

    async def _sync_subagent_tabs(self) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        pane_ids = [p.id for p in tabs.query(
            "TabPane") if p.id and p.id.startswith("sub-")]
        for pane_id in pane_ids:
            await tabs.remove_pane(pane_id)
        self._subagent_widgets.clear()
        if not self.sessions.active:
            return
        manager = self.sessions.active.subagent_manager
        manager.on_spawn = self._on_subagent_spawned
        set_subagent_manager(manager)
        for record in manager._subagents.values():
            pane = TabPane(self._tab_label(record), id=f"sub-{record.id}")
            await tabs.add_pane(pane)
            record.on_message = lambda msg, rid=record.id: self._on_subagent_message(
                rid, msg)
            record.on_state_change = lambda state, rid=record.id: self._on_subagent_state_change(
                rid, state)
            for msg in record.messages:
                await self._on_subagent_message(record.id, msg)

    @staticmethod
    def _tab_label(record: SubagentRecord) -> str:
        indicator = {"pending": "◌", "running": "●",
                     "completed": "✓", "failed": "✗",
                     "interrupted": "⊘"}
        return f"{indicator.get(record.state.value, '?')} {record.label}"

    async def rerender_footer(self) -> None:
        if not self.sessions.active:
            return

        last_usage = None
        for msg in reversed(self.sessions.active.messages):
            if msg.usage:
                last_usage = msg.usage
                break
        try:
            sidebar = self.query_one("#sidebar", Sidebar)
            if last_usage:
                sidebar.update_tokens(last_usage.prompt_tokens, last_usage.completion_tokens, last_usage.total_tokens, view_id="main")
            else:
                sidebar.update_tokens(0, 0, 0, view_id="main")
        except Exception:
            pass

        if self.model:
            self.query_one("#model", Static).update(f"{self.model}")
        else:
            self.query_one("#model", Static).update("No Model")

        await self._update_sidebar_subagents()

    async def _update_sidebar_subagents(self) -> None:
        try:
            sidebar = self.query_one("#sidebar", Sidebar)
        except Exception:
            return
        if self.sessions.active:
            records = list(self.sessions.active.subagent_manager._subagents.values())
            await sidebar.update_subagents(records)
        else:
            await sidebar.update_subagents([])
        self._manage_subagent_timer()

    def _manage_subagent_timer(self) -> None:
        has_running = self._has_running_subagents()
        if has_running and self._subagent_timer is None:
            self._subagent_timer = self.set_interval(1.0, self._tick_subagent_timer)
        elif not has_running and self._subagent_timer is not None:
            self._subagent_timer.stop()
            self._subagent_timer = None

    async def _tick_subagent_timer(self) -> None:
        await self._update_sidebar_subagents()
