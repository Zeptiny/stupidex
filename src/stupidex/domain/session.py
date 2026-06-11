from dataclasses import dataclass, field
from datetime import datetime
import uuid
from stupidex.domain.message import Message
from stupidex.agents.manager import SubagentManager


@dataclass
class Session:
    name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: list[Message] = field(default_factory=list)
    model: str | None = None
    subagent_manager: SubagentManager = field(default_factory=SubagentManager)


class SessionManager:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.active: Session | None = None

    def create(self) -> Session:
        session = Session(name=datetime.now().strftime(
            "Session %Y-%m-%d %H:%M:%S"))
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
            del self.sessions[id]
            if self.active and self.active.id == id:
                self.active = None
            return True
        return False

    def change_model(self, model_id: str) -> None:
        if self.active:
            self.active.model = model_id
