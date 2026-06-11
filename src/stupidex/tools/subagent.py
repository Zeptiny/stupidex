import time
from xml.sax.saxutils import escape

from stupidex.config import get_model_for_tier
from stupidex.domain.agent import ModelTier, TIER_DESCRIPTIONS
from stupidex.domain.tool import ExecutorResult, Tool, ToolParameter, ToolParameterProperties
from stupidex.agents import get_agent_registry
from stupidex.agents.manager import get_subagent_manager


def build_delegate_tool() -> Tool:
    registry = get_agent_registry()
    agent_lines = "\n".join(
        f"- {name} [{agent.tier.value}]: {agent.description}"
        for name, agent in registry.items()
    )
    tier_lines = "\n".join(
        f"- {tier.value}: {desc}"
        for tier, desc in TIER_DESCRIPTIONS.items()
    )
    return Tool(
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
                    description=f"The agent type to delegate to. Available agents:\n{agent_lines}"
                ),
                "tier": ToolParameterProperties(
                    type="string",
                    description=(
                        f"Override the agent's default model tier. "
                        f"The tier determines which model is used for this task. "
                        f"If omitted, the agent's predefined tier is used.\n\n"
                        f"Available tiers (from fastest to most capable):\n{tier_lines}"
                    )
                ),
            },
            required=["name", "task", "type"]
        ),
    )


async def execute_delegate_to_subagent(name: str, task: str, type: str, tier: str | None = None) -> ExecutorResult:
    registry = get_agent_registry()
    if type not in registry:
        available = ", ".join(registry.keys())
        return ExecutorResult(
            display=f"Unknown agent type: {type}",
            content=f"Error: agent type '{type}' does not exist. Available agents: {available}",
        )

    agent = registry[type]

    if tier is not None:
        try:
            resolved_tier = ModelTier.from_str(tier)
        except ValueError:
            valid = ", ".join(t.value for t in ModelTier)
            return ExecutorResult(
                display=f"Invalid tier: {tier}",
                content=f"Error: tier '{tier}' is not valid. Available tiers: {valid}",
            )
    else:
        resolved_tier = agent.tier

    model = get_model_for_tier(resolved_tier.value)
    record = await get_subagent_manager().spawn(name, task, type, model)

    return ExecutorResult(
        display=f"Subagent '{name}' spawned (id: {record.id}, tier: {resolved_tier.value})",
        content=f'<subagent id="{escape(record.id)}" name="{escape(name)}" type="{escape(type)}" tier="{escape(resolved_tier.value)}" state="pending">\n<task>\n{escape(task)}\n</task>\n</subagent>',
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

        e = escape  # shorthand
        attrs = f'id="{e(sid)}" name="{e(record.name)}" type="{e(record.type)}" state="{e(status)}" elapsed="{elapsed}s"'
        task_block = f"<task>\n{e(record.task)}\n</task>" if record.task else ""
        if record.result:
            parts.append(
                f'<subagent {attrs}>\n{task_block}\n<result>\n{e(record.result)}\n</result>\n</subagent>')
        elif record.error:
            parts.append(
                f'<subagent {attrs}>\n{task_block}\n<error>\n{e(record.error)}\n</error>\n</subagent>')
        else:
            parts.append(f'<subagent {attrs}>\n{task_block}\n</subagent>')

    found_ids = set(records.keys())
    missing = [sid for sid in subagent_ids if sid not in found_ids]
    missing_block = ""
    if missing:
        missing_block = f'\n<not_found>{", ".join(escape(sid) for sid in missing)}</not_found>'

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
        e = escape
        attrs = f'id="{e(s["id"])}" name="{e(s["name"])}" type="{e(s["type"])}" state="{e(s["state"])}" elapsed="{s["elapsed"]}s"'
        task_block = f"<task>\n{e(s['task'])}\n</task>" if s.get("task") else ""
        parts.append(f'<subagent {attrs}>\n{task_block}\n</subagent>')

    return ExecutorResult(
        display=f"{len(states)} subagent(s)",
        content="<subagents>\n" + "\n".join(parts) + "\n</subagents>",
    )
