import json
from pathlib import Path

from stupidex.config import HOME_AGENTS_DIR, PROJECT_AGENTS_DIR
from stupidex.domain.agent import Agent

AGENT_REGISTRY: dict[str, Agent] = {}


def _load_agents_from_dir(agents_dir: Path) -> dict[str, Agent]:
    agents: dict[str, Agent] = {}
    if not agents_dir.is_dir():
        return agents
    for path in sorted(agents_dir.glob("*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
            agent = Agent.from_dict(data)
            agents[agent.name] = agent
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return agents


def load_agents() -> dict[str, Agent]:
    global AGENT_REGISTRY

    home_agents = _load_agents_from_dir(HOME_AGENTS_DIR)

    project_agents_dir = Path.cwd() / PROJECT_AGENTS_DIR
    project_agents = _load_agents_from_dir(project_agents_dir)

    merged = {**home_agents, **project_agents}
    AGENT_REGISTRY = merged
    return merged


def get_agent_registry() -> dict[str, Agent]:
    if not AGENT_REGISTRY:
        return load_agents()
    return AGENT_REGISTRY
