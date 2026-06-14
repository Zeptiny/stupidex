from stupidex.domain.todo import TodoStatus, get_todo_store
from stupidex.domain.tool import ExecutorResult, Tool, ToolParameter, ToolParameterProperties

_STATUSES = ", ".join(s.value for s in TodoStatus)

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
                description=f"New status (required for 'update'). Must be one of: {_STATUSES}.",
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
    subagent_id: str | None = None,
) -> ExecutorResult:
    store = get_todo_store()

    match action:
        case "create":
            return _create(store, title, description, subagent_id)
        case "update":
            return _update(store, task_id, title, description, status, subagent_id)
        case "list":
            return _list(store, status, subagent_id)
        case "delete":
            return _delete(store, task_id)
        case _:
            return ExecutorResult(
                display="Invalid action",
                content=f"Unknown action '{action}'. Must be one of: create, update, list, delete.",
            )


def _create(store, title, description, subagent_id) -> ExecutorResult:
    if not title:
        return ExecutorResult(
            display="Missing title",
            content="Error: 'title' is required for the 'create' action.",
        )

    task = store.create(title=title, description=description or "", subagent_id=subagent_id or "")
    return ExecutorResult(
        display=f"Created task: {task.title}",
        content=f"Task created successfully.\n\nID: {task.id}\nTitle: {task.title}\nStatus: {task.status.value}",
    )


def _update(store, task_id, title, description, status, subagent_id) -> ExecutorResult:
    if not task_id:
        return ExecutorResult(
            display="Missing task_id",
            content="Error: 'task_id' is required for the 'update' action.",
        )

    parsed_status = None
    if status:
        try:
            parsed_status = TodoStatus.from_str(status)
        except ValueError as e:
            return ExecutorResult(display="Invalid status", content=f"Error: {e}")

    task, error = store.update(
        task_id,
        title=title,
        description=description,
        status=parsed_status,
        subagent_id=subagent_id,
    )
    if error:
        return ExecutorResult(display="Update failed", content=f"Error: {error}")

    changes = []
    if title is not None:
        changes.append(f"Title: {task.title}")
    if description is not None:
        changes.append(f"Description: {task.description}")
    if status:
        changes.append(f"Status: {task.status.value}")
    if subagent_id is not None:
        changes.append(f"Subagent: {task.subagent_id}")

    return ExecutorResult(
        display=f"Updated task {task.id[:8]}",
        content="Task updated successfully.\n\n" + "\n".join(changes),
    )


def _list(store, filter_status, filter_subagent_id) -> ExecutorResult:
    parsed_status = None
    if filter_status:
        try:
            parsed_status = TodoStatus.from_str(filter_status)
        except ValueError as e:
            return ExecutorResult(display="Invalid status", content=f"Error: {e}")

    tasks = store.list(status=parsed_status, subagent_id=filter_subagent_id)

    if not tasks:
        return ExecutorResult(
            display="No tasks found",
            content="No tasks match the given filters.",
        )

    lines = [f"Found {len(tasks)} task(s):\n"]
    for t in tasks:
        parts = [f"[{t.id[:8]}] {t.title}"]
        parts.append(f"  Status: {t.status.value}")
        if t.subagent_id:
            parts.append(f"  Subagent: {t.subagent_id}")
        if t.description:
            parts.append(f"  Description: {t.description[:100]}")
        lines.append("\n".join(parts) + "\n")

    return ExecutorResult(
        display=f"Found {len(tasks)} task(s)",
        content="\n".join(lines),
    )


def _delete(store, task_id) -> ExecutorResult:
    if not task_id:
        return ExecutorResult(
            display="Missing task_id",
            content="Error: 'task_id' is required for the 'delete' action.",
        )

    task = store.delete(task_id)
    if not task:
        return ExecutorResult(
            display="Task not found",
            content=f"Error: No task found with ID '{task_id}'.",
        )

    return ExecutorResult(
        display=f"Deleted task: {task.title}",
        content=f"Task '{task.id[:8]}' ({task.title}) deleted successfully.",
    )
