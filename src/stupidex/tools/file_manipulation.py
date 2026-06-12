import asyncio
import os
import difflib
import glob as glob_module
from pathlib import Path
import aiofiles
from stupidex.config import get_config
from stupidex.domain.tool import ExecutorResult, Tool, ToolParameter, ToolParameterProperties
from stupidex.utils import directory_tree

read_tool = Tool(
    name="read",
    description="Read the content of a file. Returns lines with line numbers. Use offset/limit to read specific sections of large files rather than reading the entire file.",
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
    action_label="Reading...",
)


async def execute_read_tool(file_path: str, offset: int = 1, limit: int | None = None) -> ExecutorResult:
    if limit is None:
        limit = get_config().read_line_limit
    try:
        async with aiofiles.open(file_path, "r") as f:
            lines = await f.readlines()
            # Return <line number> | <line content>
            selected_lines = lines[offset - 1:offset - 1 + limit]
            line_count = len(lines)

            if offset > line_count:
                return ExecutorResult(display=f"Offset {offset} out of range", content=f"Offset of {offset} is greater than the file line count {line_count}")

            return ExecutorResult(
                display=f"Read {file_path} lines {offset}-{min(offset + limit - 1, line_count)}",
                content=f"Showing lines {offset}-{min(offset + limit - 1, line_count)} of {line_count}\n" +
                "\n".join(f"{i + offset} | {line.rstrip()}" for i,
                          line in enumerate(selected_lines))
            )

    except Exception as e:
        return ExecutorResult(display=f"Read error {file_path}", content=f"Error reading file {file_path}: {e}")


edit_tool = Tool(
    name="edit",
    description="Replace an exact string match in a file. The old_string must be found exactly once in the file (unless replace_all is true). Use replace_all=false for targeted single edits; use replace_all=true for renaming a variable/function across a file.",
    parameters=ToolParameter(
        properties={
            "file_path": ToolParameterProperties(
                type="string",
                description="The path to the file to edit, relative to the current working directory"
            ),
            "old_string": ToolParameterProperties(
                type="string",
                description="The exact string to find and replace. Must match the file content exactly, including whitespace and indentation."
            ),
            "new_string": ToolParameterProperties(
                type="string",
                description="The replacement string"
            ),
            "replace_all": ToolParameterProperties(
                type="boolean",
                description="Whether to replace all occurrences of the old string (default: false). Use true for renames."
            ),
        },
        required=["file_path", "old_string", "new_string"]
    ),
    action_label="Editing...",
)


async def execute_edit_tool(file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> ExecutorResult:
    try:
        async with aiofiles.open(file_path, "r") as f:
            content = await f.read()

        if old_string not in content:
            return ExecutorResult(display=f"String not found in {file_path}", content=f"String '{old_string}' not found in file '{file_path}'. No changes made.")

        if replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)

        async with aiofiles.open(file_path, "w") as f:
            await f.write(new_content)

        # Generate and show the diff
        diff = difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"old/{file_path}",
            tofile=f"new/{file_path}",
            lineterm=""
        )
        diff_text = "\n".join(diff)

        display = f"Edited {file_path}"
        result = f"File '{file_path}' edited successfully."
        if diff_text:
            result += f"\n\nDiff:\n{diff_text}"
        return ExecutorResult(display=display, content=result)
    except Exception as e:
        return ExecutorResult(display=f"Edit error {file_path}", content=f"Error editing file {file_path}: {e}")


read_directory = Tool(
    name="read_directory",
    description="List the contents of a directory as a tree. Use this to understand project structure before reading individual files. Returns directory names with trailing / and file names.",
    parameters=ToolParameter(
        properties={
            "directory_path": ToolParameterProperties(
                type="string",
                description="The path to the directory to read, relative to the current working directory"
            ),
            "max_depth": ToolParameterProperties(
                type="integer",
                description="The max depth of the directory tree (Default 2)"
            ),
            "include_hidden": ToolParameterProperties(
                type="boolean",
                description="Whether to include hidden files and directories (starting with . or cache/builds/dist/envs/tooling directories) (default: false)"
            ),
        },
        required=["directory_path"]
    ),
    action_label="Browsing...",
)


async def execute_read_directory_tool(directory_path: str, max_depth: int | None = None, include_hidden: bool = False) -> ExecutorResult:
    if max_depth is None:
        max_depth = get_config().directory_tree_depth
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: directory_tree(
                path=directory_path,
                max_depth=max_depth,
                include_hidden=include_hidden,
            ),
        )
        return ExecutorResult(display=f"Read directory {directory_path}", content=result)
    except Exception as e:
        return ExecutorResult(
            display=f"Read directory error {directory_path}",
            content=f"Error reading directory {directory_path}: {e}",
        )

glob_tool = Tool(
    name="glob",
    description="Find files matching a glob pattern. Use to locate files by name when you know the pattern (e.g. '*.py', '**/*.test.ts'). Returns matching file paths sorted by modification time.",
    parameters=ToolParameter(
        properties={
            "directory_path": ToolParameterProperties(
                type="string",
                description="The directory to search in, relative to the current working directory"
            ),
            "pattern": ToolParameterProperties(
                type="string",
                description="The glob pattern to match file names (e.g., '*.py', '**/*.txt', 'src/**/*.py')"
            ),
            "include_hidden": ToolParameterProperties(
                type="boolean",
                description="Whether to include hidden files (starting with .) (default: false)"
            ),
        },
        required=["directory_path", "pattern"]
    ),
    action_label="Globbing...",
)


async def execute_glob_tool(directory_path: str, pattern: str, include_hidden: bool = False) -> ExecutorResult:
    try:
        loop = asyncio.get_event_loop()

        # Build the full pattern path
        full_pattern = os.path.join(directory_path, pattern)

        # Use glob to find matching files
        matches = await loop.run_in_executor(
            None, lambda: glob_module.glob(
                full_pattern, recursive=True, include_hidden=include_hidden)
        )

        if not matches:
            return ExecutorResult(display=f"No matches for {pattern}", content=f"No files found matching pattern '{pattern}' in '{directory_path}'.")

        # Convert to relative paths and sort
        relative_paths = sorted(matches)

        result_lines = [
            f"Found {len(relative_paths)} file(s) matching '{pattern}':"]
        for path in relative_paths:
            if os.path.isdir(path):
                result_lines.append(f"{path}/")
            else:
                result_lines.append(path)

        return ExecutorResult(display=f"Found {len(relative_paths)} matches for {pattern}", content="\n".join(result_lines))
    except Exception as e:
        return ExecutorResult(display=f"Glob error pattern: {pattern}", content=f"Error searching for files using apttern {pattern}: {e}")


write_tool = Tool(
    name="write",
    description="Create a new file or completely rewrite an existing file. Parent directories are created automatically. WARNING: This overwrites the entire file — use edit for partial changes to existing files.",
    parameters=ToolParameter(
        properties={
            "file_path": ToolParameterProperties(
                type="string",
                description="The file path, relative to the current working directory"
            ),
            "content": ToolParameterProperties(
                type="string",
                description="The complete file content to write"
            ),
        },
        required=["file_path", "content"]
    ),
    action_label="Writing...",
)


async def execute_write_tool(file_path: str, content: str) -> ExecutorResult:
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(content)

        lines = content.splitlines()
        return ExecutorResult(
            display=f"Wrote {len(lines)} lines to {path}",
            content=f"File written successfully, path: {path}, Showing lines 1-{len(lines)} of written file:\n" +
            "\n".join(f"{i + 1} | {line.rstrip()}" for i,
                      line in enumerate(lines))
        )
    except Exception as e:
        return ExecutorResult(display=f"Write error {file_path}", content=f"Error writing file: {e}")
