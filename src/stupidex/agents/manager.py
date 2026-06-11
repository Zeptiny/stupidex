import asyncio
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from stupidex.domain.agent import Agent


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
    task: str = ""
    async_task: asyncio.Task | None = None
    result: str | None = None
    error: str | None = None
    start_time: float = 0.0
    end_time: float | None = None

    @property
    def name(self) -> str:
        return self.agent.name

    @property
    def type(self) -> str:
        return self.agent.type.value


class SubagentManager:
    def __init__(self) -> None:
        self._subagents: dict[str, SubagentRecord] = {}

    async def spawn(self, name: str, task: str, agent_type: str, model: str = "mimo-v2.5") -> str:
        """Spawn a subagent as an asyncio task. Returns the subagent ID immediately."""
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
            task=task,
            start_time=time.time(),
        )
        self._subagents[subagent_id] = record

        async def _run() -> None:
            record.state = SubagentState.RUNNING
            try:
                subagent_messages = [
                    Message(role=MessageRole.USER, content=task)]
                final_content = ""
                async for msg in stream_response(
                    subagent_messages,
                    model=model,
                    available_tools=agent.available_tools,
                    system_prompt=agent.system_prompt,
                ):
                    if msg.type == MessageType.TEXT:
                        final_content = msg.content

                record.result = final_content
                record.state = SubagentState.COMPLETED
            except Exception as e:
                record.error = str(e)
                record.state = SubagentState.FAILED
            finally:
                record.end_time = time.time()

        record.async_task = asyncio.create_task(_run())
        return subagent_id

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


subagent_manager = SubagentManager()
