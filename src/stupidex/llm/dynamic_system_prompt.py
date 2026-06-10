import os
from datetime import datetime
from stupidex.domain.message import Message, MessageRole, MessageType
from stupidex.utils import directory_tree

# TODO: Improve this bullshit prompt


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

    return Message(
        role=MessageRole.SYSTEM,
        content=content,
        type=MessageType.TEXT,
    )



