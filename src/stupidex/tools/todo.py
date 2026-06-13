import fcntl
import json
import os
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from stupidex.domain.tool import ExecutorResult, Tool, ToolParameter, ToolParameterProperties

TODOS_FILE = ".stupidex_todos.json"

VALID_STATUSES = ("open", "in_progress", "blocked", "done", "abandoned", "needs_review", "under_review")
TERMINAL_STATUSES = ("done", "abandoned")

VALID_TRANSITIONS: dict[str, set[str]] = {
    "open": {"in_progress", "abandoned"},
    "in_progress": {"blocked", "done", "needs_review", "abandoned"},
    "blocked": {"in_progress", "abandoned"},
    "needs_review": {"under_review", "in_progress"},
    "under_review": {"done", "in_progress"},
}


@dataclass
class TodoTask:
    id: str
    title: str
    description: str = ""
    status: str = "open"
    assignee: str = ""
    subagent_id: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TodoTask":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def _get_todos_path() -> Path:
    return Path.cwd() / TODOS_FILE


def _load_tasks() -> list[TodoTask]:
    path = _get_todos_path()
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            data = json.load(f)
            fcntl.flock(f, fcntl.LOCK_UN)
        return [TodoTask.from_dict(t) for t in data]
    except (json.JSONDecodeError, OSError):
        return []


def _save_tasks(tasks: list[TodoTask]) -> None:
    path = _get_todos_path()
    data = [t.to_dict() for t in tasks]
    dir_path = path.parent
    os.makedirs(dir_path, exist_ok=True) if dir_path != Path(".") else None
    fd, tmp_path = tempfile.mkstemp(dir=dir_path if dir_path != Path(".") else ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_f:
            fcntl.flock(tmp_f, fcntl.LOCK_EX)
            json.dump(data, tmp_f, indent=2, ensure_ascii=False)
            tmp_f.flush()
            os.fsync(tmp_f.fileno())
            fcntl.flock(tmp_f, fcntl.LOCK_UN)
        os.replace(tmp_path, str(path))
    except Exception:
        os.unlink(tmp_path)
        raise


def _get_task_by_id(tasks: list[TodoTask], task_id: str) -> TodoTask | None:
    for t in tasks:
        if t.id == task_id:
            return t
    return None


todo_tool = Tool(
    name="todo",
    description="Manage a shared todo list for tracking tasks across subagents. Create, update, list, and delete tasks with statuses like open, in_progress, blocked, done, abandoned, needs_review, and under_review.",
    parameters=ToolParameter(
        properties={
            "action": ToolParameterProperties(
                type="string",
                description="The action to perform: 'create', 'update', 'list', or 'delete'.",
            ),
            "task_id": ToolParameterProperties(
                type="string",
                description="The ID of the task (required for 'update' and 'delete').",
            ),
            "title": ToolParameterProperties(
                type="string",
                description="Task title (required for 'create', optional for 'update').",
            ),
            "description": ToolParameterProperties(
                type="string",
                description="Task description (optional, for 'create' or 'update').",
            ),
            "status": ToolParameterProperties(
                type="string",
                description="New status (required for 'update'). Must be one of: open, in_progress, blocked, done, abandoned, needs_review, under_review.",
            ),
            "assignee": ToolParameterProperties(
                type="string",
                description="Name of the person or role assigned (optional, for 'create' or 'update').",
            ),
            "subagent_id": ToolParameterProperties(
                type="string",
                description="ID of the subagent this task belongs to (optional, for 'create' or 'update').",
            ),
        },
        required=["action"],
    ),
    action_label="Managing todos...",
)


async def execute_todo(
    action: str,
    task_id: str | None = None,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    assignee: str | None = None,
    subagent_id: str | None = None,
) -> ExecutorResult:
    match action:
        case "create":
            return await _execute_create(title, description, assignee, subagent_id)
        case "update":
            return await _execute_update(task_id, title, description, status, assignee, subagent_id)
        case "list":
            return await _execute_list(status, assignee, subagent_id)
        case "delete":
            return await _execute_delete(task_id)
        case _:
            return ExecutorResult(
                display="Invalid action",
                content=f"Unknown action '{action}'. Must be one of: create, update, list, delete.",
            )


async def _execute_create(
    title: str | None,
    description: str | None,
    assignee: str | None,
    subagent_id: str | None,
) -> ExecutorResult:
    if not title:
        return ExecutorResult(
            display="Missing title",
            content="Error: 'title' is required for the 'create' action.",
        )

    now = time.time()
    task = TodoTask(
        id=uuid.uuid4().hex,
        title=title,
        description=description or "",
        status="open",
        assignee=assignee or "",
        subagent_id=subagent_id or "",
        created_at=now,
        updated_at=now,
    )

    tasks = _load_tasks()
    tasks.append(task)
    _save_tasks(tasks)

    return ExecutorResult(
        display=f"Created task: {task.title}",
        content=f"Task created successfully.\n\nID: {task.id}\nTitle: {task.title}\nStatus: {task.status}",
    )


async def _execute_update(
    task_id: str | None,
    title: str | None,
    description: str | None,
    status: str | None,
    assignee: str | None,
    subagent_id: str | None,
) -> ExecutorResult:
    if not task_id:
        return ExecutorResult(
            display="Missing task_id",
            content="Error: 'task_id' is required for the 'update' action.",
        )

    if status and status not in VALID_STATUSES:
        return ExecutorResult(
            display="Invalid status",
            content=f"Error: '{status}' is not a valid status. Must be one of: {', '.join(VALID_STATUSES)}",
        )

    tasks = _load_tasks()
    task = _get_task_by_id(tasks, task_id)
    if not task:
        return ExecutorResult(
            display="Task not found",
            content=f"Error: No task found with ID '{task_id}'.",
        )

    if task.status in TERMINAL_STATUSES:
        return ExecutorResult(
            display="Task is terminal",
            content=f"Error: Task '{task_id}' is in terminal status '{task.status}' and cannot be updated.",
        )

    if status:
        allowed = VALID_TRANSITIONS.get(task.status, set())
        if status not in allowed:
            return ExecutorResult(
                display="Invalid transition",
                content=(
                    f"Error: Cannot transition from '{task.status}' to '{status}'. "
                    f"Allowed transitions: {', '.join(sorted(allowed)) or 'none'}"
                ),
            )
        task.status = status

    if title is not None:
        task.title = title
    if description is not None:
        task.description = description
    if assignee is not None:
        task.assignee = assignee
    if subagent_id is not None:
        task.subagent_id = subagent_id

    task.updated_at = time.time()
    _save_tasks(tasks)

    changes = []
    if title is not None:
        changes.append(f"Title: {task.title}")
    if description is not None:
        changes.append(f"Description: {task.description}")
    if status:
        changes.append(f"Status: {task.status}")
    if assignee is not None:
        changes.append(f"Assignee: {task.assignee}")
    if subagent_id is not None:
        changes.append(f"Subagent: {task.subagent_id}")

    return ExecutorResult(
        display=f"Updated task {task.id[:8]}",
        content=f"Task updated successfully.\n\n" + "\n".join(changes),
    )


async def _execute_list(
    filter_status: str | None,
    filter_assignee: str | None,
    filter_subagent_id: str | None,
) -> ExecutorResult:
    tasks = _load_tasks()

    if filter_status:
        tasks = [t for t in tasks if t.status == filter_status]
    if filter_assignee:
        tasks = [t for t in tasks if t.assignee == filter_assignee]
    if filter_subagent_id:
        tasks = [t for t in tasks if t.subagent_id == filter_subagent_id]

    if not tasks:
        return ExecutorResult(
            display="No tasks found",
            content="No tasks match the given filters.",
        )

    lines = [f"Found {len(tasks)} task(s):\n"]
    for t in tasks:
        parts = [f"[{t.id[:8]}] {t.title}"]
        parts.append(f"  Status: {t.status}")
        if t.assignee:
            parts.append(f"  Assignee: {t.assignee}")
        if t.subagent_id:
            parts.append(f"  Subagent: {t.subagent_id}")
        if t.description:
            parts.append(f"  Description: {t.description[:100]}")
        lines.append("\n".join(parts) + "\n")

    return ExecutorResult(
        display=f"Found {len(tasks)} task(s)",
        content="\n".join(lines),
    )


async def _execute_delete(task_id: str | None) -> ExecutorResult:
    if not task_id:
        return ExecutorResult(
            display="Missing task_id",
            content="Error: 'task_id' is required for the 'delete' action.",
        )

    tasks = _load_tasks()
    task = _get_task_by_id(tasks, task_id)
    if not task:
        return ExecutorResult(
            display="Task not found",
            content=f"Error: No task found with ID '{task_id}'.",
        )

    tasks = [t for t in tasks if t.id != task_id]
    _save_tasks(tasks)

    return ExecutorResult(
        display=f"Deleted task: {task.title}",
        content=f"Task '{task.id[:8]}' ({task.title}) deleted successfully.",
    )
