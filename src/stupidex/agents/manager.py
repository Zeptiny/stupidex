from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable, Coroutine
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from stupidex.domain.agent import Agent

if TYPE_CHECKING:
    from stupidex.domain.message import Message

log = logging.getLogger(__name__)

_current_manager: ContextVar[SubagentManager] = ContextVar('current_manager')


def _log_task_exception(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.error("Unhandled exception in background task: %s", exc, exc_info=exc)


def _fire_and_forget(coro: Coroutine) -> asyncio.Task:
    task = asyncio.create_task(coro)
    task.add_done_callback(_log_task_exception)
    return task


def get_subagent_manager() -> SubagentManager:
    return _current_manager.get()


def set_subagent_manager(manager: SubagentManager) -> None:
    _current_manager.set(manager)


class SubagentState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


SUBAGENT_INDICATORS: dict[SubagentState, str] = {
    SubagentState.PENDING: "◌",
    SubagentState.RUNNING: "●",
    SubagentState.COMPLETED: "✓",
    SubagentState.FAILED: "✗",
    SubagentState.INTERRUPTED: "⊘",
}


@dataclass
class SubagentRecord:
    id: str
    agent: Agent
    state: SubagentState
    label: str = ""
    task: str = ""
    async_task: asyncio.Task | None = None
    result: str | None = None
    error: str | None = None
    start_time: float = 0.0
    end_time: float | None = None
    messages: list[Message] = field(default_factory=list)
    messages_mounted: int = 0
    on_message: Callable[[Message], Coroutine[Any, Any, None]] | None = None
    on_state_change: Callable[[SubagentState],
                              Coroutine[Any, Any, None]] | None = None

    @property
    def name(self) -> str:
        return self.agent.name

    @property
    def type(self) -> str:
        return self.agent.type.value


class SubagentManager:
    def __init__(self) -> None:
        self._subagents: dict[str, SubagentRecord] = {}
        self.on_spawn: Callable[[SubagentRecord],
                                Coroutine[Any, Any, None]] | None = None

    def cancel_one(self, subagent_id: str) -> bool:
        """Cancel a single subagent by ID. Returns True if cancelled."""
        record = self._subagents.get(subagent_id)
        if record and record.async_task and not record.async_task.done():
            record.async_task.cancel()
            return True
        return False

    def cancel_all(self) -> list[str]:
        """Cancel all running subagents. Returns list of cancelled IDs."""
        cancelled = []
        for record in self._subagents.values():
            if record.async_task and not record.async_task.done():
                record.async_task.cancel()
                cancelled.append(record.id)
        self.on_spawn = None
        return cancelled

    def cancel_running(self) -> list[str]:
        """Cancel all non-terminal subagents. Returns list of cancelled IDs."""
        terminal = {SubagentState.COMPLETED, SubagentState.FAILED, SubagentState.INTERRUPTED}
        cancelled = []
        for record in self._subagents.values():
            if record.state not in terminal and record.async_task and not record.async_task.done():
                record.async_task.cancel()
                cancelled.append(record.id)
        return cancelled

    async def spawn(self, name: str, task: str, agent_type: str, model: str | None = None) -> SubagentRecord:
        """Spawn a subagent as an asyncio task. Returns the record immediately."""
        # Lazy imports to avoid circular dependency
        from stupidex.agents import get_agent_registry
        from stupidex.domain.message import Message, MessageRole, MessageType
        from stupidex.llm.client import stream_response

        registry = get_agent_registry()
        if agent_type not in registry:
            raise ValueError(
                f"Unknown agent type: {agent_type}. Available: {', '.join(registry.keys())}"
            )

        agent = registry[agent_type]
        subagent_id = uuid.uuid4().hex[:12]

        record = SubagentRecord(
            id=subagent_id,
            agent=agent,
            state=SubagentState.PENDING,
            label=name,
            task=task,
            start_time=time.time(),
        )
        self._subagents[subagent_id] = record

        async def _run() -> None:
            record.state = SubagentState.RUNNING
            if record.on_state_change:
                _fire_and_forget(record.on_state_change(record.state))
            try:
                user_msg = Message(role=MessageRole.USER, content=task)
                subagent_messages = [user_msg]
                record.messages.append(user_msg)
                if record.on_message:
                    record.messages_mounted += 1
                    try:
                        await record.on_message(user_msg)
                    except Exception:
                        pass
                async for msg in stream_response(
                    subagent_messages,
                    model=model,
                    available_tools=agent.available_tools,
                    system_prompt=agent.system_prompt,
                ):
                    record.messages.append(msg)
                    if record.on_message:
                        record.messages_mounted += 1
                        try:
                            await record.on_message(msg)
                        except Exception:
                            pass
                    if msg.type == MessageType.TEXT:
                        record.result = msg.content

                record.state = SubagentState.COMPLETED
            except asyncio.CancelledError:
                record.error = "Interrupted by user"
                record.state = SubagentState.INTERRUPTED
                raise
            except Exception as e:
                record.error = str(e)
                record.state = SubagentState.FAILED
            finally:
                record.end_time = time.time()
                if record.on_state_change:
                    _fire_and_forget(record.on_state_change(record.state))

        record.async_task = None  # set below
        if self.on_spawn:
            _fire_and_forget(self.on_spawn(record))
        record.async_task = asyncio.create_task(_run())
        return record

    async def wait(self, ids: list[str]) -> dict[str, SubagentRecord]:
        """Wait for all specified subagents to complete. Returns their records."""
        tasks = []
        for sid in ids:
            record = self._subagents.get(sid)
            if record and record.async_task and not record.async_task.done():
                tasks.append(record.async_task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        return {sid: self._subagents[sid] for sid in ids if sid in self._subagents}

    def get_states(self) -> list[dict]:
        """Return state info for all tracked subagents."""
        states = []
        for record in self._subagents.values():
            elapsed = None
            if record.end_time:
                elapsed = round(record.end_time - record.start_time, 1)
            elif record.start_time:
                elapsed = round(time.time() - record.start_time, 1)

            states.append({
                "id": record.id,
                "name": record.name,
                "type": record.type,
                "task": record.task,
                "state": record.state.value,
                "elapsed": elapsed,
            })
        return states

    def get_record(self, subagent_id: str) -> SubagentRecord | None:
        """Look up a single subagent record by ID."""
        return self._subagents.get(subagent_id)

    def all_records(self) -> list[SubagentRecord]:
        """Return all subagent records."""
        return list(self._subagents.values())
