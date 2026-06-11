from stupidex.tools.file_manipulation import read_tool, execute_read_tool, edit_tool, execute_edit_tool, read_directory, execute_read_directory_tool, glob_tool, execute_glob_tool, write_tool, execute_write_tool
from stupidex.tools.search import grep_tool, execute_grep_tool
from stupidex.tools.exec import execute_command_tool, execute_command
from stupidex.tools.subagent import build_delegate_tool, execute_delegate_to_subagent, wait_for_subagent, execute_wait_for_subagent, list_subagents, execute_list_subagents


def get_tool_registry() -> dict[str, dict]:
    return {
        "read": {"tool": read_tool, "executor": execute_read_tool},
        "edit": {"tool": edit_tool, "executor": execute_edit_tool},
        "read_directory": {"tool": read_directory, "executor": execute_read_directory_tool},
        "glob": {"tool": glob_tool, "executor": execute_glob_tool},
        "write": {"tool": write_tool, "executor": execute_write_tool},
        "grep": {"tool": grep_tool, "executor": execute_grep_tool},
        "execute_command": {"tool": execute_command_tool, "executor": execute_command},
        "delegate_to_subagent": {"tool": build_delegate_tool(), "executor": execute_delegate_to_subagent},
        "wait_for_subagent": {"tool": wait_for_subagent, "executor": execute_wait_for_subagent},
        "list_subagents": {"tool": list_subagents, "executor": execute_list_subagents},
    }
