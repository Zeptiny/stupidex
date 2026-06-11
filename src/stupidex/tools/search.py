import asyncio
import os
import re
from stupidex.config import get_config
from stupidex.domain.tool import ExecutorResult, Tool, ToolParameter, ToolParameterProperties
from stupidex.utils import get_ignored_dirs
import aiofiles

grep_tool = Tool(
    name="grep",
    description="Search for a pattern in files within a directory and return matching lines with file paths and line numbers",
    parameters=ToolParameter(
        properties={
            "pattern": ToolParameterProperties(
                type="string",
                description="The regex pattern to search for"
            ),
            "directory_path": ToolParameterProperties(
                type="string",
                description="The directory to search in, relative to the current working directory"
            ),
            "include_pattern": ToolParameterProperties(
                type="string",
                description="Glob pattern to filter files (e.g., '*.py', '*.txt'). If not set, all files are searched."
            ),
            "case_insensitive": ToolParameterProperties(
                type="boolean",
                description="Whether the search should be case insensitive (default: false)"
            ),
            "max_results": ToolParameterProperties(
                type="integer",
                description="Maximum number of matching lines to return (default: 100)"
            ),
        },
        required=["pattern", "directory_path"]
    ),
)


async def _is_binary(file_path: str) -> bool:
    """Check if a file is binary by reading a small chunk."""
    try:
        async with aiofiles.open(file_path, "rb") as f:
            chunk = await f.read(8192)
            return b"\0" in chunk
    except OSError:
        return True


def _should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped based on ignored_dirs config."""
    ignored = get_ignored_dirs()
    if dirname in ignored:
        return True
    if dirname.startswith("."):
        return True
    return False


async def execute_grep_tool(
    pattern: str,
    directory_path: str,
    include_pattern: str | None = None,
    case_insensitive: bool = False,
    max_results: int | None = None,
) -> ExecutorResult:
    if max_results is None:
        max_results = get_config().grep_max_results
    """Search for a pattern in files within a directory."""
    try:
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return ExecutorResult(
                display=f"Invalid regex: {pattern}",
                content=f"Error: Invalid regex pattern '{pattern}': {e}",
            )

        base_path = os.path.abspath(directory_path)
        if not os.path.isdir(base_path):
            return ExecutorResult(
                display=f"Directory not found: {directory_path}",
                content=f"Error: Directory '{directory_path}' does not exist.",
            )

        # If include_pattern is given, compile it as a regex for matching filenames
        file_regex = None
        if include_pattern:
            # Convert simple glob to regex: *.py -> .*\.py$
            glob_regex = include_pattern.replace(".", r"\.").replace("*", ".*")
            file_regex = re.compile(f"^{glob_regex}$", re.IGNORECASE)

        results: list[str] = []
        total_matches = 0

        # Collect all file paths using os.walk (blocking) in executor
        def _collect_files():
            collected = []
            for root, dirs, files in os.walk(base_path):
                dirs[:] = [d for d in dirs if not _should_skip_dir(d)]
                for filename in sorted(files):
                    if file_regex and not file_regex.match(filename):
                        continue
                    collected.append(os.path.join(root, filename))
            return collected

        loop = asyncio.get_event_loop()
        file_paths = await loop.run_in_executor(None, _collect_files)

        for file_path in file_paths:
            if total_matches >= max_results:
                break

            # Skip binary files
            if await _is_binary(file_path):
                continue

            try:
                relative_path = os.path.relpath(file_path, base_path)
                async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    line_num = 0
                    async for line in f:
                        line_num += 1
                        if regex.search(line):
                            results.append(
                                f"{relative_path}:{line_num}: {line.rstrip()}")
                            total_matches += 1
                            if total_matches >= max_results:
                                break
            except (PermissionError, OSError):
                continue

        if not results:
            return ExecutorResult(
                display=f"No matches for '{pattern}'",
                content=f"No matches found for pattern '{pattern}' in '{directory_path}'.",
            )

        output_lines = [
            f"Found {total_matches} match(es) for pattern '{pattern}':"]
        output_lines.extend(results)

        if total_matches >= max_results:
            output_lines.append(f"\n... (truncated to {max_results} results)")

        return ExecutorResult(
            display=f"Found {total_matches} matches for '{pattern}'",
            content="\n".join(output_lines),
        )

    except Exception as e:
        return ExecutorResult(
            display=f"Grep error: {pattern}",
            content=f"Error searching for pattern '{pattern}': {e}",
        )
