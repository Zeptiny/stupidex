from stupidex.domain.message import Message, MessageRole, MessageType
from stupidex.domain.tool import ExecutorResult, Tool, ToolParameter, ToolParameterProperties
from stupidex.agents import AGENT_REGISTRY

_agent_options = "\n".join(
    f"- {name}: {agent.description}" for name, agent in AGENT_REGISTRY.items())

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


def execute_delegate_to_subagent(name: str, task: str, type: str, model: str = "mimo-v2.5") -> ExecutorResult:
    # Lazy imports to avoid circular dependency
    from stupidex.llm.client import stream_response
    from stupidex.tools import TOOL_REGISTRY

    if type not in AGENT_REGISTRY:
        available = ", ".join(AGENT_REGISTRY.keys())
        return ExecutorResult(
            display=f"Unknown agent type: {type}",
            content=f"Error: agent type '{type}' does not exist. Available agents: {available}",
        )

    agent = AGENT_REGISTRY[type]
    subagent_messages = [Message(role=MessageRole.USER, content=task)]
    system_prompt = agent.system_prompt

    # Prevent from having undefined/inexistent tools
    filtered_tools = {k: v for k, v in TOOL_REGISTRY.items()
                      if k in agent.available_tools}

    final_content = ""
    for msg in stream_response(
        subagent_messages,
        model=model,
        tools=filtered_tools,
        system_prompt=system_prompt,
    ):
        if msg.type == MessageType.TEXT:
            final_content = msg.content

    return ExecutorResult(
        display=f"Subagent '{name}' completed",
        content=final_content,
    )
