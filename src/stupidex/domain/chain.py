import time
from dataclasses import dataclass, field
from enum import Enum

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
