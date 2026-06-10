from stupidex.tools.file_manipulation import read_tool, execute_read_tool, edit_tool, execute_edit_tool, read_directory, execute_read_directory_tool, glob_tool, execute_glob_tool, write_tool, execute_write_tool

TOOL_REGISTRY = {
    "read": {"tool": read_tool, "executor": execute_read_tool},
    "edit": {"tool": edit_tool, "executor": execute_edit_tool},
    "read_directory": {"tool": read_directory, "executor": execute_read_directory_tool},
    "glob": {"tool": glob_tool, "executor": execute_glob_tool},
    "write": {"tool": write_tool, "executor": execute_write_tool},
}
