from stupidex.domain.tool import Tool, ToolParameter, ToolParameterProperties
from stupidex.utils import directory_tree


read_tool = Tool(
    name="read",
    description="Read the content of a file in the current working directory",
    parameters=ToolParameter(
        properties={
            "file_path": ToolParameterProperties(
                type="string",
                description="The path to the file to read, relative to the current working directory"
            ),
            "offset": ToolParameterProperties(
                type="integer",
                description="The line number to start from (default: 1, 1 indexed)"
            ),
            "limit": ToolParameterProperties(
                type="integer",
                description="The maximum number of lines to read (default: 100)"
            ),
        },
        required=["file_path"]
    ),
)


def execute_read_tool(file_path: str, offset: int = 1, limit: int = 100) -> str:
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
            # Return <line number> | <line content>
            selected_lines = lines[offset - 1:offset - 1 + limit]
            return "\n".join(f"{i + offset} | {line.rstrip()}" for i, line in enumerate(selected_lines))

    except Exception as e:
        return f"Error reading file: {e}"


edit_tool = Tool(
    name="edit",
    description="Edit a file in the current working directory",
    parameters=ToolParameter(
        properties={
            "file_path": ToolParameterProperties(
                type="string",
                description="The path to the file to edit, relative to the current working directory"
            ),
            "old_string": ToolParameterProperties(
                type="string",
                description="The string to be replaced in the file"
            ),
            "new_string": ToolParameterProperties(
                type="string",
                description="The new string to replace the old string"
            ),
            "replace_all": ToolParameterProperties(
                type="boolean",
                description="Whether to replace all occurrences of the old string (default: false)"
            ),
        },
        required=["file_path", "old_string", "new_string"]
    ),
)

# TODO: Show the edit diff


def execute_edit_tool(file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    try:
        with open(file_path, "r") as f:
            content = f.read()

        if old_string not in content:
            return f"String '{old_string}' not found in file '{file_path}'. No changes made."

        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)

        with open(file_path, "w") as f:
            f.write(new_content)

        return f"File '{file_path}' edited successfully."
    except Exception as e:
        return f"Error editing file: {e}"


read_directory = Tool(
    name="read_directory",
    description="Read the contents of a directory",
    parameters=ToolParameter(
        properties={
            "directory_path": ToolParameterProperties(
                type="string",
                description="The path to the directory to read, relative to the current working directory"
            ),
            "max_depth": ToolParameterProperties(
                type="integer",
                description="The max depth of the directory tree (Default 2)"
            )
        },
        required=["directory_path"]
    ),
)


def execute_read_directory_tool(directory_path: str, max_depth: int = 2) -> str:
    return directory_tree(path=directory_path, max_depth=max_depth)
