import os
import re
from stupidex.domain.tool import ExecutorResult, Tool, ToolParameter, ToolParameterProperties
from stupidex.utils import IGNORED_DIRS

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


def _is_binary(file_path: str) -> bool:
    """Check if a file is binary by reading a small chunk."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(8192)
            return b"\0" in chunk
    except OSError:
        return True


def _should_skip_dir(dirname: str) -> bool:
    """Check if a directory should be skipped based on IGNORED_DIRS rules."""
    if dirname in IGNORED_DIRS:
        return True
    if dirname.startswith("."):
        return True
    return False


def execute_grep_tool(
    pattern: str,
    directory_path: str,
    include_pattern: str | None = None,
    case_insensitive: bool = False,
    max_results: int = 100,
) -> ExecutorResult:
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
        files_searched = 0
        total_matches = 0

        for root, dirs, files in os.walk(base_path):
            # Prune ignored directories in-place so os.walk skips them
            dirs[:] = [d for d in dirs if not _should_skip_dir(d)]

            for filename in sorted(files):
                if total_matches >= max_results:
                    break

                # Filter by include pattern
                if file_regex and not file_regex.match(filename):
                    continue

                file_path = os.path.join(root, filename)

                # Skip binary files
                if _is_binary(file_path):
                    continue

                try:
                    relative_path = os.path.relpath(file_path, base_path)
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                results.append(f"{relative_path}:{line_num}: {line.rstrip()}")
                                total_matches += 1
                                if total_matches >= max_results:
                                    break
                except (PermissionError, OSError):
                    continue

            files_searched += 1
            if total_matches >= max_results:
                break

        if not results:
            return ExecutorResult(
                display=f"No matches for '{pattern}'",
                content=f"No matches found for pattern '{pattern}' in '{directory_path}'.",
            )

        output_lines = [f"Found {total_matches} match(es) for pattern '{pattern}':"]
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
