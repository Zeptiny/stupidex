from stupidex.domain.todo import TodoStatus, get_todo_store
from stupidex.domain.tool import ExecutorResult, Tool, ToolParameter, ToolParameterProperties

_STATUSES = ", ".join(s.value for s in TodoStatus)

todo_create_tool = Tool(
    name="todo_create",
    description="Create a new task in the shared todo list.",
    parameters=ToolParameter(
        properties={
            "title": ToolParameterProperties(
                type="string",
                description="Task title.",
            ),
            "description": ToolParameterProperties(
                type="string",
                description="Task description (optional).",
            ),
            "subagent_id": ToolParameterProperties(
                type="string",
                description="ID of the subagent this task belongs to (optional).",
            ),
        },
        required=["title"],
    ),
    action_label="Creating todo...",
)

todo_update_tool = Tool(
    name="todo_update",
    description="Update an existing task in the shared todo list.",
    parameters=ToolParameter(
        properties={
            "task_id": ToolParameterProperties(
                type="string",
                description="The ID of the task to update.",
            ),
            "title": ToolParameterProperties(
                type="string",
                description="New title (optional).",
            ),
            "description": ToolParameterProperties(
                type="string",
                description="New description (optional).",
            ),
            "status": ToolParameterProperties(
                type="string",
                description=f"New status. Must be one of: {_STATUSES}.",
            ),
            "subagent_id": ToolParameterProperties(
                type="string",
                description="New subagent ID (optional).",
            ),
        },
        required=["task_id"],
    ),
    action_label="Updating todo...",
)

todo_list_tool = Tool(
    name="todo_list",
    description="List tasks in the shared todo list, optionally filtered by status or subagent.",
    parameters=ToolParameter(
        properties={
            "status": ToolParameterProperties(
                type="string",
                description=f"Filter by status. Must be one of: {_STATUSES}.",
            ),
            "subagent_id": ToolParameterProperties(
                type="string",
                description="Filter by subagent ID.",
            ),
        },
        required=[],
    ),
    action_label="Listing todos...",
)

todo_delete_tool = Tool(
    name="todo_delete",
    description="Delete a task from the shared todo list.",
    parameters=ToolParameter(
        properties={
            "task_id": ToolParameterProperties(
                type="string",
                description="The ID of the task to delete.",
            ),
        },
        required=["task_id"],
    ),
    action_label="Deleting todo...",
)


async def execute_todo_create(
    title: str,
    description: str | None = None,
    subagent_id: str | None = None,
) -> ExecutorResult:
    store = get_todo_store()
    task = store.create(title=title, description=description or "", subagent_id=subagent_id or "")
    return ExecutorResult(
        display=f"Created task: {task.title}",
        content=f"Task created successfully.\n\nID: {task.id}\nTitle: {task.title}\nStatus: {task.status.value}",
    )


async def execute_todo_update(
    task_id: str,
    title: str | None = None,
    description: str | None = None,
    status: str | None = None,
    subagent_id: str | None = None,
) -> ExecutorResult:
    store = get_todo_store()

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


async def execute_todo_list(
    status: str | None = None,
    subagent_id: str | None = None,
) -> ExecutorResult:
    store = get_todo_store()

    parsed_status = None
    if status:
        try:
            parsed_status = TodoStatus.from_str(status)
        except ValueError as e:
            return ExecutorResult(display="Invalid status", content=f"Error: {e}")

    tasks = store.list(status=parsed_status, subagent_id=subagent_id)

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


async def execute_todo_delete(
    task_id: str,
) -> ExecutorResult:
    store = get_todo_store()
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
