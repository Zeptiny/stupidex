from textual.app import App, ComposeResult
from textual.containers import Horizontal, ScrollableContainer
from textual.widgets import Input, LoadingIndicator, Static, TabbedContent, TabPane

from stupidex.commands.session_commands import SessionCommands
from stupidex.domain.message import Message, MessageRole, MessageType
from stupidex.domain.session import SessionManager
from stupidex.llm.client import stream_response
from stupidex.widgets.message_widget import (
    AssistantMessageWidget,
    ThinkingMessageWidget,
    ToolCallMessageWidget,
    ToolResultMessageWidget,
    UserMessageWidget,
    create_message_widget,
)
from stupidex.agents import get_agent_registry
from stupidex.agents.manager import set_subagent_manager, SubagentRecord, SubagentState


class Stupidex(App):
    CSS_PATH = "main.tcss"
    BINDINGS = [("ctrl+p", "command_palette", "Commands")]
    COMMANDS = {SessionCommands}

    sessions: SessionManager = SessionManager()
    _subagent_widgets: dict[str, dict[str,
                                      ThinkingMessageWidget | AssistantMessageWidget | None]] = {}

    @property
    def messages(self) -> list[Message]:
        return self.sessions.active.messages if self.sessions.active else []

    @property
    def model(self) -> str | None:
        return self.sessions.active.model if self.sessions.active else None

    def compose(self) -> ComposeResult:
        with Horizontal(id="header"):
            yield Static(self.sessions.active.name if self.sessions.active else "No Session", id="title")
        with TabbedContent(id="tabs", initial="main"):
            with TabPane("Main", id="main"):
                yield ScrollableContainer(id="output")
        yield Input(id="input")
        with Horizontal(id="footer"):
            yield LoadingIndicator(id="spinner")
            yield Static("N/A Model", id="model")
            yield Static("Context: 0 | Response: 0 | Total: 0", id="status")

    async def on_mount(self) -> None:
        self.sessions.create()
        self.query_one("#title", Static).update(self.sessions.active.name)
        await self.mount_all_messages()
        self.query_one("#input", Input).display = True
        self.query_one("#input", Input).focus()
        self.rerender_footer()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        user_msg = event.value
        event.input.clear()
        msg = Message(role=MessageRole.USER, content=user_msg)
        self.messages.append(msg)
        await self.mount_message(msg)
        self.streaming_started()
        self.run_worker(self._stream_response())

    async def _stream_response(self) -> None:
        container = self.query_one("#output", ScrollableContainer)

        thinking_widget: ThinkingMessageWidget | None = None
        content_widget: AssistantMessageWidget | None = None

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
                    widget = ToolCallMessageWidget(msg)
                    await container.mount(widget)
                    widget.scroll_visible()
                    thinking_widget = None
                    content_widget = None
                elif msg.type == MessageType.TOOL_RESULT:
                    self.messages.append(msg)
                    widget = ToolResultMessageWidget(msg)
                    await container.mount(widget)
                    widget.scroll_visible()
                    thinking_widget = None
                    content_widget = None
                else:
                    if content_widget is None:
                        self.messages.append(msg)
                        content_widget = AssistantMessageWidget(msg)
                        await container.mount(content_widget)
                        content_widget.scroll_visible()
                    else:
                        content_widget.update_content(msg.content)
                        content_widget.msg.usage = msg.usage
        finally:
            self.streaming_finished()

    def streaming_started(self) -> None:
        self.query_one("#spinner").display = True

    def streaming_finished(self) -> None:
        self.query_one("#spinner").display = False
        self.rerender_footer()

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

    async def _on_subagent_message(self, subagent_id: str, msg: Message) -> None:
        try:
            pane = self.query_one(f"#sub-{subagent_id}", TabPane)
        except Exception:
            return
        try:
            container = pane.query_one(ScrollableContainer)
        except Exception:
            container = ScrollableContainer()
            await pane.mount(container)

        widgets = self._subagent_widgets.setdefault(subagent_id, {})
        thinking_widget = widgets.get("thinking")
        content_widget = widgets.get("content")

        if msg.type == MessageType.THINKING:
            if thinking_widget is None:
                w = ThinkingMessageWidget(msg)
                await container.mount(w)
                widgets["thinking"] = w
                w.scroll_visible()
            else:
                thinking_widget.update_content(msg.content)
                thinking_widget.refresh()
        elif msg.type == MessageType.TOOL_CALL:
            w = ToolCallMessageWidget(msg)
            await container.mount(w)
            w.scroll_visible()
            widgets["thinking"] = None
            widgets["content"] = None
        elif msg.type == MessageType.TOOL_RESULT:
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
                w = AssistantMessageWidget(msg)
                await container.mount(w)
                widgets["content"] = w
                w.scroll_visible()
            else:
                content_widget.update_content(msg.content)
                content_widget.refresh()

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

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        input_widget = self.query_one("#input", Input)
        input_widget.display = event.pane.id == "main"

    async def mount_message(self, msg: Message) -> None:
        container = self.query_one("#output", ScrollableContainer)
        widget = create_message_widget(msg)
        await container.mount(widget)
        widget.scroll_visible()

    async def mount_all_messages(self) -> None:
        container = self.query_one("#output", ScrollableContainer)
        await container.remove_children()
        for msg in self.messages:
            widget = create_message_widget(msg)
            await container.mount(widget)

    async def rerender_all(self) -> None:
        if not self.sessions.active:
            return

        self.query_one("#title", Static).update(self.sessions.active.name)
        await self.mount_all_messages()
        await self._sync_subagent_tabs()
        self.rerender_footer()

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
                     "completed": "✓", "failed": "✗"}
        return f"{indicator.get(record.state.value, '?')} {record.label}"

    def rerender_footer(self) -> None:
        if not self.sessions.active:
            return

        last_msg = self.sessions.active.messages[-1] if self.sessions.active.messages else None
        if last_msg and last_msg.usage:
            u = last_msg.usage
            self.query_one("#status", Static).update(
                f"Context: {u.prompt_tokens} | Response: {u.completion_tokens} | Total: {u.total_tokens}"
            )
        else:
            self.query_one("#status", Static).update(
                "Context: 0 | Response: 0 | Total: 0")

        if self.model:
            self.query_one("#model", Static).update(f"{self.model}")
        else:
            self.query_one("#model", Static).update("No Model")
