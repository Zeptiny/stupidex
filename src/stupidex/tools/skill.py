from xml.sax.saxutils import escape

from stupidex.domain.tool import ExecutorResult, Tool, ToolParameter, ToolParameterProperties
from stupidex.skills import get_skill_registry


def build_skill_tool() -> Tool:
    registry = get_skill_registry()
    skill_lines = "\n".join(
        f"- {name}: {skill.description}"
        for name, skill in registry.items()
    )
    return Tool(
        name="skill",
        description="Load a specialized skill when the task at hand matches one of the skills listed in the system prompt. Use this tool to inject the skill's instructions and resources into current conversation. The output may contain detailed workflow guidance as well as references to scripts, files, etc in the same directory as the skill.",
        parameters=ToolParameter(
            properties={
                "name": ToolParameterProperties(
                    type="string",
                    description=f"The name of the skill from available_skills. Available skills:\n{skill_lines}"
                ),
            },
            required=["name"]
        ),
        action_label="Loading skill...",
    )


async def execute_skill(name: str) -> ExecutorResult:
    registry = get_skill_registry()
    if name not in registry:
        available = ", ".join(registry.keys())
        return ExecutorResult(
            display=f"Unknown skill: {name}",
            content=f"Error: skill '{name}' does not exist. Available skills: {available}",
        )

    skill = registry[name]
    e = escape

    skill_content = skill.content if skill.content else f"Skill '{name}' loaded (no content file found at location)"

    content = (
        f'<skill_content name="{e(skill.name)}">\n'
        f'{e(skill_content)}\n'
        f'</skill_content>'
    )

    return ExecutorResult(
        display=f"Skill '{name}' loaded",
        content=content,
    )


def build_list_skills_tool() -> Tool:
    return Tool(
        name="list_skills",
        description="List all available skills with their descriptions. Use to discover what skills are available before loading one.",
        parameters=ToolParameter(properties={}, required=[]),
        action_label="Listing skills...",
    )


async def execute_list_skills() -> ExecutorResult:
    registry = get_skill_registry()

    if not registry:
        return ExecutorResult(display="No skills available", content="<skills />")

    e = escape
    parts = []
    for name, skill in registry.items():
        parts.append(f'<skill name="{e(name)}">\n{e(skill.description)}\n</skill>')

    content = "<skills>\n" + "\n".join(parts) + "\n</skills>"

    return ExecutorResult(
        display=f"{len(registry)} skill(s) available",
        content=content,
    )
