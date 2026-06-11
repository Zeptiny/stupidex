import time

from stupidex.domain.tool import ExecutorResult, Tool, ToolParameter, ToolParameterProperties
from stupidex.agents import AGENT_REGISTRY, AgentTypes
from stupidex.agents.manager import get_subagent_manager

_agent_options = "\n".join(
    f"- {name}: {agent.description} (tools: {', '.join(agent.available_tools)})"
    for name, agent in AGENT_REGISTRY.items() if agent.type == AgentTypes.SUBAGENT)

delegate_to_subagent = Tool(
    name="delegate_to_subagent",
    description="Delegate a task to a subagent. Subagents do not share context and must be given explicit instructions.",
    parameters=ToolParameter(
        properties={
            "name": ToolParameterProperties(
                type="string",
                description="A descriptive name for this subagent instance"
            ),
            "task": ToolParameterProperties(
                type="string",
                description="The subagent task with detailed instructions"
            ),
            "type": ToolParameterProperties(
                type="string",
                description=f"The agent type. Available types:\n{_agent_options}"
            ),
            "model": ToolParameterProperties(
                type="string",
                description="The model to use for the subagent, default mimo-v2.5"
            ),
        },
        required=["name", "task", "type"]
    ),
)


async def execute_delegate_to_subagent(name: str, task: str, type: str, model: str = "mimo-v2.5") -> ExecutorResult:
    if type not in AGENT_REGISTRY:
        available = ", ".join(AGENT_REGISTRY.keys())
        return ExecutorResult(
            display=f"Unknown agent type: {type}",
            content=f"Error: agent type '{type}' does not exist. Available agents: {available}",
        )

    subagent_id = await get_subagent_manager().spawn(name, task, type, model)

    return ExecutorResult(
        display=f"Subagent '{name}' spawned (id: {subagent_id})",
        content=f'<subagent id="{subagent_id}" name="{name}" type="{type}" state="pending">\n<task>\n{task}\n</task>\n</subagent>',
    )


wait_for_subagent = Tool(
    name="wait_for_subagent",
    description="Wait for one or more subagents to complete and get their results",
    parameters=ToolParameter(
        properties={
            "subagent_ids": ToolParameterProperties(
                type="array",
                description="List of subagent IDs to wait for",
                items={"type": "string"},
            ),
        },
        required=["subagent_ids"]
    ),
)


async def execute_wait_for_subagent(subagent_ids: list[str]) -> ExecutorResult:
    if not subagent_ids:
        return ExecutorResult(display="No subagent IDs provided", content="Error: subagent_ids must be a non-empty list of IDs.")

    records = await get_subagent_manager().wait(subagent_ids)

    if not records:
        return ExecutorResult(display="No subagents found", content=f"No subagents found for IDs: {', '.join(subagent_ids)}")

    parts = []
    for sid, record in records.items():
        status = record.state.value
        elapsed = None
        if record.end_time:
            elapsed = round(record.end_time - record.start_time, 1)
        elif record.start_time:
            elapsed = round(time.time() - record.start_time, 1)

        attrs = f'id="{sid}" name="{record.name}" type="{record.type}" state="{status}" elapsed="{elapsed}s"'
        task_block = f"<task>\n{record.task}\n</task>" if record.task else ""
        if record.result:
            parts.append(
                f'<subagent {attrs}>\n{task_block}\n<result>\n{record.result}\n</result>\n</subagent>')
        elif record.error:
            parts.append(
                f'<subagent {attrs}>\n{task_block}\n<error>\n{record.error}\n</error>\n</subagent>')
        else:
            parts.append(f'<subagent {attrs}>\n{task_block}\n</subagent>')

    found_ids = set(records.keys())
    missing = [sid for sid in subagent_ids if sid not in found_ids]
    missing_block = ""
    if missing:
        missing_block = f'\n<not_found>{", ".join(missing)}</not_found>'

    content = "<subagents>\n" + \
        "\n".join(parts) + f"\n</subagents>{missing_block}"

    return ExecutorResult(
        display=f"Waited for {len(records)} subagent(s)",
        content=content,
    )


list_subagents = Tool(
    name="list_subagents",
    description="List all subagents and their current states",
    parameters=ToolParameter(properties={}, required=[]),
)


async def execute_list_subagents() -> ExecutorResult:
    states = get_subagent_manager().get_states()

    if not states:
        return ExecutorResult(display="No subagents", content="<subagents />")

    parts = []
    for s in states:
        attrs = f'id="{s["id"]}" name="{s["name"]}" type="{s["type"]}" state="{s["state"]}" elapsed="{s["elapsed"]}s"'
        task_block = f"<task>\n{s['task']}\n</task>" if s.get("task") else ""
        parts.append(f'<subagent {attrs}>\n{task_block}\n</subagent>')

    return ExecutorResult(
        display=f"{len(states)} subagent(s)",
        content="<subagents>\n" + "\n".join(parts) + "\n</subagents>",
    )
