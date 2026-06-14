from stupidex.tools.exec import execute_command, execute_command_tool
from stupidex.tools.file_manipulation import (
    edit_tool,
    execute_edit_tool,
    execute_glob_tool,
    execute_read_directory_tool,
    execute_read_tool,
    execute_write_tool,
    glob_tool,
    read_directory,
    read_tool,
    write_tool,
)
from stupidex.tools.search import execute_grep_tool, grep_tool
from stupidex.tools.skill import (
    build_list_skills_tool,
    build_skill_tool,
    execute_list_skills,
    execute_skill,
)
from stupidex.tools.subagent import (
    build_delegate_tool,
    execute_delegate_to_subagent,
    execute_interrupt_subagents,
    execute_list_subagents,
    execute_wait_for_subagent,
    interrupt_subagents,
    list_subagents,
    wait_for_subagent,
)
from stupidex.tools.todo import (
    execute_todo_create,
    execute_todo_delete,
    execute_todo_list,
    execute_todo_update,
    todo_create_tool,
    todo_delete_tool,
    todo_list_tool,
    todo_update_tool,
)

_TOOL_REGISTRY: dict[str, dict] | None = None


def get_tool_registry() -> dict[str, dict]:
    global _TOOL_REGISTRY
    if _TOOL_REGISTRY is not None:
        return _TOOL_REGISTRY
    _TOOL_REGISTRY = {
        "read": {"tool": read_tool, "executor": execute_read_tool},
        "edit": {"tool": edit_tool, "executor": execute_edit_tool},
        "read_directory": {"tool": read_directory, "executor": execute_read_directory_tool},
        "glob": {"tool": glob_tool, "executor": execute_glob_tool},
        "write": {"tool": write_tool, "executor": execute_write_tool},
        "grep": {"tool": grep_tool, "executor": execute_grep_tool},
        "todo_create": {"tool": todo_create_tool, "executor": execute_todo_create},
        "todo_update": {"tool": todo_update_tool, "executor": execute_todo_update},
        "todo_list": {"tool": todo_list_tool, "executor": execute_todo_list},
        "todo_delete": {"tool": todo_delete_tool, "executor": execute_todo_delete},
        "execute_command": {"tool": execute_command_tool, "executor": execute_command},
        "delegate_to_subagent": {"tool": build_delegate_tool(), "executor": execute_delegate_to_subagent},
        "wait_for_subagent": {"tool": wait_for_subagent, "executor": execute_wait_for_subagent},
        "list_subagents": {"tool": list_subagents, "executor": execute_list_subagents},
        "interrupt_subagents": {"tool": interrupt_subagents, "executor": execute_interrupt_subagents},
        "skill": {"tool": build_skill_tool(), "executor": execute_skill},
        "list_skills": {"tool": build_list_skills_tool(), "executor": execute_list_skills},
    }
    return _TOOL_REGISTRY


def reset_tool_registry() -> None:
    """Call after agents/skills change to rebuild on next access."""
    global _TOOL_REGISTRY
    _TOOL_REGISTRY = None
