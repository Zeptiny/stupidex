import os
from datetime import datetime
from xml.sax.saxutils import escape
from stupidex.domain.message import Message, MessageRole, MessageType
from stupidex.utils import directory_tree
from stupidex.agents.manager import get_subagent_manager


def build_dynamic_system_prompt() -> Message:
    cwd = os.getcwd()
    tree = directory_tree(cwd, max_depth=2)

    content = f"""
<current_time>{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</current_time>
<working_directory>{cwd}</working_directory>
<directory_structure>
{tree}
</directory_structure>
"""

    subagent_manager = get_subagent_manager()
    states = subagent_manager.get_states()
    if states:
        parts = []
        for s in states:
            e = escape
            attrs = f'id="{e(s["id"])}" name="{e(s["name"])}" type="{e(s["type"])}" state="{e(s["state"])}" elapsed="{s["elapsed"]}s"'
            task_block = f"<task>\n{e(s['task'])}\n</task>" if s.get(
                "task") else ""
            parts.append(
                f'  <subagent {attrs}>\n  {task_block}\n  </subagent>')
        content += "\n<subagents>\n" + "\n".join(parts) + "\n</subagents>\n"

    return Message(
        role=MessageRole.SYSTEM,
        content=content,
        type=MessageType.TEXT,
    )
