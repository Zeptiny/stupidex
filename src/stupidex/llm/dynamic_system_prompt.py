import os
from datetime import datetime
from stupidex.domain.message import Message, MessageRole, MessageType

# TODO: Improve this bullshit prompt


def build_dynamic_system_prompt() -> Message:
    cwd = os.getcwd()
    tree = _directory_tree(cwd, max_depth=2)

    content = f"""
<current_time>{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</current_time>
<working_directory>{cwd}</working_directory>
<directory_structure>
{tree}
</directory_structure>
"""

    return Message(
        role=MessageRole.SYSTEM,
        content=content,
        type=MessageType.TEXT,
    )


def _directory_tree(path: str, max_depth: int, _depth: int = 0, _prefix: str = "") -> str:
    if _depth >= max_depth:
        return ""

    lines = []
    try:
        entries = sorted(os.listdir(path))
    except PermissionError:
        return ""

    entries = [e for e in entries if not e.startswith(".")]

    for i, entry in enumerate(entries):
        full_path = os.path.join(path, entry)
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        child_prefix = "    " if is_last else "│   "

        if os.path.isdir(full_path):
            lines.append(f"{_prefix}{connector}{entry}/")
            lines.append(_directory_tree(full_path, max_depth,
                         _depth + 1, _prefix + child_prefix))
        else:
            lines.append(f"{_prefix}{connector}{entry}")

    return "\n".join(line for line in lines if line)
