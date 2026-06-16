import asyncio
import logging
from enum import Enum

from textual.app import App, ComposeResult
from textual.containers import Horizontal, ScrollableContainer
from textual.widgets import LoadingIndicator, Static, TabbedContent, TabPane, TextArea

from stupidex.agents import get_agent_registry
from stupidex.commands.session_commands import SessionCommands, execute_command
from stupidex.config import get_current_theme
from stupidex.domain.chain import Chain, ChainStatus
from stupidex.domain.message import Message, MessageRole, MessageType, StreamHistoryState, record_streamed_message
from stupidex.domain.session import SessionManager
from stupidex.domain.todo import get_todo_store, set_todo_refresh_callback, set_todo_store
from stupidex.llm.client import classify_error, stream_response
from stupidex.personality import append_personality
from stupidex.themes import get_theme_registry
from stupidex.widgets.command_picker import CommandPicker
from stupidex.widgets.message_widget import (
    ChainContainer,
    StreamWidgetState,
    create_message_widget,
    mount_streamed_message,
)
from stupidex.widgets.sidebar import NavEntry, Sidebar, SidebarMainSelected, SidebarSubagentSelected
from stupidex.widgets.subagent_ui import SubagentUIManager

log = logging.getLogger(__name__)


class InterruptState(Enum):
    IDLE = "idle"
    CONFIRM_AGENT = "confirm_agent"
    CONFIRM_SUBAGENTS = "confirm_subagents"


class InputTextArea(TextArea):
    _app_ref: "Stupidex | None" = None

    def _on_resize(self) -> None:
        super()._on_resize()
        if self._app_ref is not None:
            self._app_ref._update_input_height(self)


class Stupidex(App):
    CSS_PATH = "main.tcss"
    BINDINGS = [
        ("ctrl+p", "command_palette", "Commands"),
        ("escape", "interrupt", "Interrupt"),
        ("ctrl+s", "submit_input", "Submit"),
        ("ctrl+c", "clear_input", "Clear Input"),
        ("ctrl+b", "toggle_sidebar_focus", "Toggle Sidebar"),
    ]
    COMMANDS = {SessionCommands}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sessions: SessionManager = SessionManager()
        self._interrupt_state: InterruptState = InterruptState.IDLE
        self._active_worker: object | None = None
        self._subagent_ui = SubagentUIManager(self)
        self._current_chain: ChainContainer | None = None
        self._footer_timer: object | None = None
        self._setup_themes()

    def _setup_themes(self) -> None:
        registry = get_theme_registry()
        for name in registry.list_themes():
            self.register_theme(registry.get(name))
        current = get_current_theme()
        if current in registry.list_themes():
            self.theme = registry.get(current).name

    def switch_theme(self, name: str) -> None:
        registry = get_theme_registry()
        theme = registry.get(name)
        self.theme = theme.name

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
        yield CommandPicker(SessionCommands.COMMANDS)
        yield InputTextArea(id="input")
        with Horizontal(id="footer"):
            yield LoadingIndicator(id="spinner")
            yield Static("N/A Model", id="model")
            yield Static("", id="interrupt-hint")
        yield Sidebar(id="sidebar")

    async def on_mount(self) -> None:
        self.sessions.create()
        set_todo_store(self.sessions.active.todo_store)
        set_todo_refresh_callback(self.refresh_todos)
        self.query_one("#title", Static).update(self.sessions.active.name)
        await self.mount_all_messages()
        text_area = self.query_one("#input", InputTextArea)
        text_area._app_ref = self
        text_area.display = True
        self._update_input_height(text_area)
        text_area.focus()
        try:
            sidebar = self.query_one("#sidebar", Sidebar)
            sidebar.set_active("main")
        except Exception:
            pass
        await self.rerender_footer()
        await self.refresh_todos()
        from stupidex.config import get_config
        from stupidex.mcp import MCPManager, set_mcp_manager
        cfg = get_config()
        if cfg.mcp_servers:
            mcp_manager = MCPManager()
            await mcp_manager.start_all(cfg.mcp_servers)
            set_mcp_manager(mcp_manager)
            self._mcp_manager = mcp_manager

    async def on_exit(self) -> None:
        if hasattr(self, '_mcp_manager') and self._mcp_manager is not None:
            try:
                await self._mcp_manager.shutdown()
            except Exception:
                pass

    def _is_streaming(self) -> bool:
        return self._active_worker is not None and not self._active_worker.is_finished

    def _has_running_subagents(self) -> bool:
        if not self.sessions.active:
            return False
        return self._subagent_ui.has_running(self.sessions.active.subagent_manager)

    async def action_interrupt(self) -> None:
        try:
            picker = self.query_one("#command-picker", CommandPicker)
            if picker.display:
                picker.hide()
                return
        except Exception:
            pass

        hint = self.query_one("#interrupt-hint", Static)

        if self._interrupt_state == InterruptState.IDLE:
            if self._is_streaming():
                self._interrupt_state = InterruptState.CONFIRM_AGENT
                hint.update("[bold yellow]Press Esc again to interrupt agent[/]")
            elif self._has_running_subagents():
                self._interrupt_state = InterruptState.CONFIRM_SUBAGENTS
                hint.update("[bold red]Press Esc again to interrupt subagents[/]")
        elif self._interrupt_state == InterruptState.CONFIRM_AGENT:
            self._interrupt_state = InterruptState.CONFIRM_SUBAGENTS
            if self._active_worker and not self._active_worker.is_finished:
                self._active_worker.cancel()
            if self._has_running_subagents():
                hint.update("[bold red]Press Esc again to interrupt subagents[/]")
            else:
                self._interrupt_state = InterruptState.IDLE
                hint.update("")
        elif self._interrupt_state == InterruptState.CONFIRM_SUBAGENTS:
            if self.sessions.active:
                cancelled = self.sessions.active.subagent_manager.cancel_running()
                if cancelled:
                    names = []
                    for sid in cancelled:
                        record = self.sessions.active.subagent_manager.get_record(sid)
                        if record:
                            names.append(record.label or record.name)
                    detail = ", ".join(names) if names else f"{len(cancelled)} subagent(s)"
                    interrupt_msg = Message(
                        role=MessageRole.ASSISTANT,
                        content=f"[Subagents interrupted by user: {detail}]",
                    )
                    if self._current_chain:
                        self._current_chain.chain.messages.append(interrupt_msg)
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

        picker = self.query_one("#command-picker", CommandPicker)
        if picker.display and user_msg.startswith("/"):
            command = picker.get_selected_command()
            text_area.clear()
            picker.hide()
            if command:
                await execute_command(self, command)
            return

        text_area.clear()
        self._start_chain()
        msg = Message(role=MessageRole.USER, content=user_msg)
        self._current_chain.chain.messages.append(msg)
        await self.mount_message(msg)
        self._reset_interrupt_state()
        self.streaming_started()
        self._active_worker = self.run_worker(self._stream_response(), exit_on_error=False)

    _INPUT_MAX_CONTENT_ROWS = 3

    def _update_input_height(self, text_area: TextArea) -> None:
        line_count = text_area.wrapped_document.height if text_area.soft_wrap else text_area.document.line_count
        content_rows = max(1, min(line_count, self._INPUT_MAX_CONTENT_ROWS))
        text_area.set_styles(height=content_rows + 2)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id != "input":
            return
        self._update_input_height(event.text_area)
        text = event.text_area.text.strip()
        try:
            picker = self.query_one("#command-picker", CommandPicker)
        except Exception:
            return
        if text.startswith("/"):
            picker.update_filter(text)
        elif picker.display:
            picker.hide()

    async def on_command_picker_command_selected(self, event: CommandPicker.CommandSelected) -> None:
        text_area = self.query_one("#input", TextArea)
        text_area.clear()
        self.query_one("#command-picker", CommandPicker).hide()
        await execute_command(self, event.command)

    def watch_focused(self, focused) -> None:
        if focused and focused.id == "input":
            try:
                picker = self.query_one("#command-picker", CommandPicker)
                if picker.display:
                    picker.hide()
            except Exception:
                pass

    def action_clear_input(self) -> None:
        self.query_one("#input", TextArea).clear()

    def action_toggle_sidebar_focus(self) -> None:
        focused = self.focused
        if isinstance(focused, NavEntry):
            self._switch_to_main_view()
            self.query_one("#input", TextArea).focus()
        else:
            try:
                sidebar = self.query_one("#sidebar", Sidebar)
                entries = sidebar._get_focusable_entries()
                if entries:
                    entries[0].focus()
            except Exception:
                pass

    def _switch_to_main_view(self) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = "main"
        self.query_one("#input", TextArea).display = True
        sidebar = self.query_one("#sidebar", Sidebar)
        sidebar.set_active("main")

    async def _stream_response(self) -> None:
        output = self.query_one("#output", ScrollableContainer)
        container = self._current_chain.messages_area if self._current_chain else output

        ws = StreamWidgetState()
        history_state = StreamHistoryState()

        self._subagent_ui.setup(self.sessions.active.subagent_manager)

        try:
            general = get_agent_registry()["general"]
            system_prompt = append_personality(general.system_prompt)
            async for msg in stream_response(
                messages=self.messages,
                model=self.model,
                allowed_tools=general.allowed_tools,
                system_prompt=system_prompt,
                allowed_skills=general.allowed_skills,
            ):
                record_streamed_message(self._current_chain.chain.messages, msg, history_state)

                await mount_streamed_message(container, msg, ws)

                if ws.content and msg.usage:
                    ws.content.msg.usage = msg.usage
                if msg.usage:
                    await self.rerender_footer()
        except asyncio.CancelledError:
            interrupted_msg = Message(
                role=MessageRole.ASSISTANT,
                content="[Interrupted by user]",
            )
            if self._current_chain:
                self._current_chain.chain.messages.append(interrupted_msg)
            self._freeze_chain(ChainStatus.INTERRUPTED)
            for tw in ws.temp:
                try:
                    await tw.remove()
                except Exception:
                    pass
            ws.temp.clear()
            try:
                await self.mount_message(interrupted_msg)
            except Exception:
                pass
            raise
        except Exception as exc:
            self._freeze_chain(ChainStatus.FAILED)
            log.exception("Stream response failed")
            for tw in ws.temp:
                try:
                    await tw.remove()
                except Exception:
                    pass
            ws.temp.clear()
            try:
                title, detail = classify_error(exc)
                error_msg = Message(
                    role=MessageRole.ASSISTANT,
                    content=detail,
                    type=MessageType.ERROR,
                    metadata={"error_title": title},
                )
            except Exception:
                error_msg = Message(
                    role=MessageRole.ASSISTANT,
                    content=str(exc)[:200] or type(exc).__name__,
                    type=MessageType.ERROR,
                    metadata={"error_title": "Unexpected Error"},
                )
            try:
                await mount_streamed_message(container, error_msg, ws)
            except Exception:
                log.exception("Failed to mount error widget")
        finally:
            await self.streaming_finished()

    def _start_chain(self) -> None:
        chain = Chain(model=self.model)
        if self.sessions.active:
            self.sessions.active.chains.append(chain)
        container = self.query_one("#output", ScrollableContainer)
        self._current_chain = ChainContainer(chain)
        container.mount(self._current_chain)

    async def _mount_in_chain(self, msg: Message) -> None:
        widget = create_message_widget(msg)
        if widget is None:
            return
        if self._current_chain and self._current_chain.messages_area:
            await self._current_chain.messages_area.mount(widget)
            widget.scroll_visible()
        else:
            container = self.query_one("#output", ScrollableContainer)
            await container.mount(widget)
            widget.scroll_visible()

    def streaming_started(self) -> None:
        self.query_one("#spinner").display = True
        self._footer_timer = self.set_interval(1.0, self._tick_footer)

    async def streaming_finished(self) -> None:
        self.query_one("#spinner").display = False
        self._freeze_chain()
        if self._interrupt_state != InterruptState.CONFIRM_SUBAGENTS:
            self._reset_interrupt_state()
        await self.rerender_footer()

    def _freeze_chain(self, status: ChainStatus = ChainStatus.COMPLETED) -> None:
        if self._footer_timer:
            self._footer_timer.stop()
            self._footer_timer = None
        if self._current_chain:
            self._current_chain.chain.finish(status)
            self._current_chain.freeze()
            self._current_chain = None

    async def _tick_footer(self) -> None:
        if self._current_chain:
            self._current_chain.tick()
        await self.rerender_footer()

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
        await self._mount_in_chain(msg)

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
        await self._subagent_ui.sync_tabs(self.sessions.active.subagent_manager)
        await self.rerender_footer()
        await self.refresh_todos()

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
                sidebar.update_tokens(
                    last_usage.prompt_tokens, last_usage.completion_tokens, last_usage.total_tokens, view_id="main"
                )
            else:
                sidebar.update_tokens(0, 0, 0, view_id="main")
        except Exception:
            pass

        model_label = self.model or "No Model"
        self.query_one("#model", Static).update(model_label)

        await self._subagent_ui.update_sidebar()

    async def refresh_todos(self) -> None:
        try:
            store = get_todo_store()
            sidebar = self.query_one("#sidebar", Sidebar)
            await sidebar.update_todos(store.list())
        except Exception:
            pass
