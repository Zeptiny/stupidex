from __future__ import annotations

import asyncio
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Callable, Any, Coroutine

from stupidex.domain.agent import Agent

if TYPE_CHECKING:
    from stupidex.domain.message import Message

_current_manager: ContextVar['SubagentManager'] = ContextVar('current_manager')


def get_subagent_manager() -> 'SubagentManager':
    return _current_manager.get()


def set_subagent_manager(manager: 'SubagentManager') -> None:
    _current_manager.set(manager)


class SubagentState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


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

    async def spawn(self, name: str, task: str, agent_type: str, model: str = "mimo-v2.5") -> SubagentRecord:
        """Spawn a subagent as an asyncio task. Returns the record immediately."""
        # Lazy imports to avoid circular dependency
        from stupidex.llm.client import stream_response
        from stupidex.domain.message import Message, MessageRole, MessageType
        from stupidex.agents import AGENT_REGISTRY

        if agent_type not in AGENT_REGISTRY:
            raise ValueError(
                f"Unknown agent type: {agent_type}. Available: {', '.join(AGENT_REGISTRY.keys())}"
            )

        agent = AGENT_REGISTRY[agent_type]
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
                asyncio.create_task(record.on_state_change(record.state))
            try:
                user_msg = Message(role=MessageRole.USER, content=task)
                subagent_messages = [user_msg]
                record.messages.append(user_msg)
                if record.on_message:
                    record.messages_mounted += 1
                    await record.on_message(user_msg)
                async for msg in stream_response(
                    subagent_messages,
                    model=model,
                    available_tools=agent.available_tools,
                    system_prompt=agent.system_prompt,
                ):
                    record.messages.append(msg)
                    if record.on_message:
                        record.messages_mounted += 1
                        await record.on_message(msg)
                    if msg.type == MessageType.TEXT:
                        record.result = msg.content

                record.state = SubagentState.COMPLETED
            except Exception as e:
                record.error = str(e)
                record.state = SubagentState.FAILED
            finally:
                record.end_time = time.time()
                if record.on_state_change:
                    asyncio.create_task(record.on_state_change(record.state))

        record.async_task = None  # set below
        if self.on_spawn:
            asyncio.create_task(self.on_spawn(record))
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
