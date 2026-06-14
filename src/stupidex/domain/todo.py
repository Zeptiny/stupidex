from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Coroutine
from contextvars import ContextVar
from dataclasses import dataclass
from enum import Enum
from typing import Any


class TodoStatus(Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    ABANDONED = "abandoned"
    NEEDS_REVIEW = "needs_review"
    UNDER_REVIEW = "under_review"

    @classmethod
    def from_str(cls, value: str) -> TodoStatus:
        _map = {s.value: s for s in cls}
        result = _map.get(value.lower())
        if result is None:
            valid = ", ".join(s.value for s in cls)
            raise ValueError(f"Invalid status: '{value}'. Valid statuses: {valid}")
        return result


TERMINAL_STATUSES: set[TodoStatus] = {TodoStatus.DONE, TodoStatus.ABANDONED}

VALID_TRANSITIONS: dict[TodoStatus, set[TodoStatus]] = {
    TodoStatus.OPEN: {TodoStatus.IN_PROGRESS, TodoStatus.ABANDONED},
    TodoStatus.IN_PROGRESS: {TodoStatus.BLOCKED, TodoStatus.DONE, TodoStatus.NEEDS_REVIEW, TodoStatus.ABANDONED},
    TodoStatus.BLOCKED: {TodoStatus.IN_PROGRESS, TodoStatus.ABANDONED},
    TodoStatus.NEEDS_REVIEW: {TodoStatus.UNDER_REVIEW, TodoStatus.IN_PROGRESS},
    TodoStatus.UNDER_REVIEW: {TodoStatus.DONE, TodoStatus.IN_PROGRESS},
}


@dataclass
class TodoTask:
    id: str
    title: str
    description: str = ""
    status: TodoStatus = TodoStatus.OPEN
    subagent_id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "subagent_id": self.subagent_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class TodoStore:
    def __init__(self) -> None:
        self._tasks: dict[str, TodoTask] = {}

    def create(
        self,
        title: str,
        description: str = "",
        subagent_id: str = "",
    ) -> TodoTask:
        now = time.time()
        task = TodoTask(
            id=uuid.uuid4().hex,
            title=title,
            description=description,
            status=TodoStatus.OPEN,
            subagent_id=subagent_id,
            created_at=now,
            updated_at=now,
        )
        self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> TodoTask | None:
        return self._tasks.get(task_id)

    def list(
        self,
        status: TodoStatus | None = None,
        subagent_id: str | None = None,
    ) -> list[TodoTask]:
        tasks = list(self._tasks.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        if subagent_id is not None:
            tasks = [t for t in tasks if t.subagent_id == subagent_id]
        return tasks

    def update(
        self,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        status: TodoStatus | None = None,
        subagent_id: str | None = None,
    ) -> tuple[TodoTask | None, str | None]:
        """Update a task. Returns (task, error). On success error is None."""
        task = self._tasks.get(task_id)
        if task is None:
            return None, f"No task found with ID '{task_id}'."

        if task.status in TERMINAL_STATUSES:
            return None, f"Task '{task_id}' is in terminal status '{task.status.value}' and cannot be updated."

        if status is not None:
            allowed = VALID_TRANSITIONS.get(task.status, set())
            if status not in allowed:
                targets = ", ".join(s.value for s in sorted(allowed, key=lambda s: s.value))
                return None, f"Cannot transition from '{task.status.value}' to '{status.value}'. Allowed: {targets or 'none'}"
            task.status = status

        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if subagent_id is not None:
            task.subagent_id = subagent_id

        task.updated_at = time.time()
        return task, None

    def delete(self, task_id: str) -> TodoTask | None:
        return self._tasks.pop(task_id, None)


_current_store: ContextVar[TodoStore] = ContextVar("current_store")


def get_todo_store() -> TodoStore:
    return _current_store.get()


def set_todo_store(store: TodoStore) -> None:
    _current_store.set(store)


_todo_refresh_callback: Callable[[], Coroutine[Any, Any, None]] | None = None


def set_todo_refresh_callback(cb: Callable[[], Coroutine[Any, Any, None]]) -> None:
    global _todo_refresh_callback
    _todo_refresh_callback = cb


async def notify_todo_changed() -> None:
    if _todo_refresh_callback:
        await _todo_refresh_callback()
