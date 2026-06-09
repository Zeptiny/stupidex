from dataclasses import dataclass, field
from .message import Message


@dataclass
class Session:
    name: str
    messages: list[Message] = field(default_factory=list)


class SessionManager:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.active: Session | None = None

    def create(self, name: str) -> Session:
        session = Session(name=name)
        self.sessions[name] = session
        self.active = session
        return session

    def switch(self, name: str) -> Session | None:
        if name in self.sessions:
            self.active = self.sessions[name]
            return self.active
        return None

    def delete(self, name: str) -> bool:
        if name in self.sessions:
            del self.sessions[name]
            if self.active and self.active.name == name:
                self.active = None
            return True
        return False

    def list(self) -> list[str]:
        return list(self.sessions.keys())
