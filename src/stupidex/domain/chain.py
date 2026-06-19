import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from stupidex.domain.message import Message


class ChainStatus(Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


@dataclass
class Chain:
    model: str | None = None
    messages: list[Message] = field(default_factory=list)
    start_time: float = field(default_factory=time.monotonic)
    end_time: float | None = None
    status: ChainStatus = ChainStatus.RUNNING

    @property
    def elapsed(self) -> float:
        end = self.end_time if self.end_time else time.monotonic()
        return end - self.start_time

    def finish(self, status: ChainStatus = ChainStatus.COMPLETED) -> None:
        if self.status != ChainStatus.RUNNING:
            return
        self.end_time = time.monotonic()
        self.status = status

    @staticmethod
    def format_elapsed(seconds: float) -> str:
        if seconds < 1:
            return f"{seconds * 1000:.0f}ms"
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.0f}s"

    def to_storage_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [m.to_storage_dict() for m in self.messages],
            "start_time": self.start_time,
            "end_time": self.end_time,
            "status": self.status.value,
        }

    @classmethod
    def from_storage_dict(cls, data: dict[str, Any]) -> "Chain":
        chain = cls(
            model=data.get("model"),
            messages=[Message.from_storage_dict(m) for m in data.get("messages", [])],
            start_time=data.get("start_time", 0.0),
            end_time=data.get("end_time"),
            status=ChainStatus(data.get("status", "completed")),
        )
        return chain
