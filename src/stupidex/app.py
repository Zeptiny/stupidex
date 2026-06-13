import asyncio
from enum import Enum

from textual.app import App, ComposeResult
from textual.containers import Horizontal, ScrollableContainer
from textual.widgets import LoadingIndicator, Static, TabbedContent, TabPane, TextArea

from stupidex.agents import get_agent_registry
from stupidex.agents.manager import SubagentState
from stupidex.commands.session_commands import SessionCommands, execute_command
from stupidex.config import get_current_theme
from stupidex.domain.message import Message, MessageRole, MessageType
from stupidex.domain.session import SessionManager
from stupidex.llm.client import stream_response
from stupidex.personality import append_personality
from stupidex.themes import get_theme_registry
from stupidex.widgets.command_picker import CommandPicker
from stupidex.widgets.message_widget import (
    AssistantMessageWidget,
    ThinkingMessageWidget,
    ToolResultMessageWidget,
    create_message_widget,
    get_tool_action_label,
)
from stupidex.widgets.sidebar import NavEntry, Sidebar, SidebarMainSelected, SidebarSubagentSelected
from stupidex.widgets.subagent_ui import SubagentUIManager


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
        ("ctrl+b", "toggle_sidebar_focus", "Toggle Sidebar"),
    ]
    COMMANDS = {SessionCommands}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sessions: SessionManager = SessionManager()
        self._interrupt_state: InterruptState = InterruptState.IDLE
        self._active_worker: object | None = None
        self._subagent_ui = SubagentUIManager(self)
        self._setup_themes()

    def _setup_themes(self) -> None:
        registry = get_theme_registry()
        for name in registry.list_themes():
            self.register_theme(registry.get(name))
        current = get_current_theme()
        if current in registry.list_themes():
            self.theme = current

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

        picker = self.query_one("#command-picker", CommandPicker)
        if picker.display and user_msg.startswith("/"):
            command = picker.get_selected_command()
            text_area.clear()
            picker.hide()
            if command:
                await execute_command(self, command)
            return

        text_area.clear()
        msg = Message(role=MessageRole.USER, content=user_msg)
        self.messages.append(msg)
        await self.mount_message(msg)
        self._reset_interrupt_state()
        self.streaming_started()
        self._active_worker = self.run_worker(self._stream_response(), exit_on_error=False)

    async def on_submittextarea_submitted(self, event: TextArea.Submitted) -> None:
        await self.action_submit_input()

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id != "input":
            return
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
        container = self.query_one("#output", ScrollableContainer)

        thinking_widget: ThinkingMessageWidget | None = None
        content_widget: AssistantMessageWidget | None = None
        temp_widgets: list[Static] = []

        self._subagent_ui.setup(self.sessions.active.subagent_manager)

        try:
            general = get_agent_registry()["general"]
            system_prompt = append_personality(general.system_prompt)
            async for msg in stream_response(
                messages=self.messages,
                model=self.model,
                available_tools=general.available_tools,
                system_prompt=system_prompt,
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
        await self._subagent_ui.sync_tabs(self.sessions.active.subagent_manager)
        await self.rerender_footer()

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

        if self.model:
            self.query_one("#model", Static).update(f"{self.model}")
        else:
            self.query_one("#model", Static).update("No Model")

        await self._subagent_ui.update_sidebar()
