import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from stupidex.agents.manager import SubagentManager, SubagentRecord
from stupidex.config import get_config
from stupidex.domain.chain import Chain
from stupidex.domain.message import Message
from stupidex.domain.todo import TodoStore

log = logging.getLogger(__name__)


@dataclass
class Session:
    name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    chains: list[Chain] = field(default_factory=list)
    model: str | None = None
    subagent_manager: SubagentManager = field(default_factory=SubagentManager)
    todo_store: TodoStore = field(default_factory=TodoStore)

    @property
    def messages(self) -> list[Message]:
        return [msg for chain in self.chains for msg in chain.messages]

    def to_storage_dict(self) -> dict[str, Any]:
        subagent_records = []
        for record in self.subagent_manager.all_records():
            subagent_records.append(record.to_storage_dict())
        return {
            "version": 1,
            "id": self.id,
            "name": self.name,
            "model": self.model,
            "chains": [c.to_storage_dict() for c in self.chains],
            "subagent_chains": subagent_records,
            "todo_store": self.todo_store.to_storage_dict(),
        }

    @classmethod
    def from_storage_dict(cls, data: dict[str, Any]) -> "Session":
        chains = [Chain.from_storage_dict(c) for c in data.get("chains", [])]
        todo_store = TodoStore.from_storage_dict(data.get("todo_store", {}))
        session = cls(
            id=data["id"],
            name=data["name"],
            model=data.get("model"),
            chains=chains,
            todo_store=todo_store,
        )
        for sd in data.get("subagent_chains", []):
            try:
                record = SubagentRecord.from_storage_dict(sd)
                session.subagent_manager._subagents[record.id] = record
            except Exception:
                log.warning("Failed to restore subagent record %s", sd, exc_info=True)
        return session


class SessionManager:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.active: Session | None = None

    def create(self) -> Session:
        cfg = get_config()
        session = Session(
            name=datetime.now().strftime("Session %Y-%m-%d %H:%M:%S"),
            model=cfg.default_model,
        )
        self.sessions[session.id] = session
        self.active = session
        return session

    def switch(self, id: str) -> Session | None:
        if id in self.sessions:
            self.active = self.sessions[id]
            return self.active
        return None

    def delete(self, id: str) -> bool:
        if id in self.sessions:
            session = self.sessions[id]
            session.subagent_manager.cancel_all()
            del self.sessions[id]
            if self.active and self.active.id == id:
                self.active = None
            from stupidex.storage import delete_session
            delete_session(id)
            return True
        return False

    def change_model(self, model_id: str) -> None:
        if self.active:
            self.active.model = model_id

    def save_active(self) -> None:
        """Persist the active session to disk."""
        if not self.active:
            return
        from stupidex.storage import save_session
        save_session(self.active.to_storage_dict())

    def load(self, session_id: str) -> Session | None:
        """Load a session from disk into memory and set it active."""
        from stupidex.storage import load_session
        data = load_session(session_id)
        if data is None:
            return None
        try:
            session = Session.from_storage_dict(data)
        except Exception:
            log.warning("Failed to deserialize session %s", session_id, exc_info=True)
            return None
        self.sessions[session.id] = session
        self.active = session
        return session

    def list_saved(self) -> list[dict]:
        """List all saved sessions from disk."""
        from stupidex.storage import list_saved_sessions
        return list_saved_sessions()
