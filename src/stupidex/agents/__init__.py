import json
import logging
from pathlib import Path

from stupidex.config import HOME_AGENTS_DIR, PROJECT_AGENTS_DIR
from stupidex.domain.agent import Agent

log = logging.getLogger(__name__)

AGENT_REGISTRY: dict[str, Agent] = {}

_REQUIRED_FIELDS = {"name", "type", "description", "system_prompt", "available_tools"}

_DEFAULT_AGENTS: dict[str, dict] = {
    "general": {
        "name": "general",
        "type": "internal",
        "tier": "papudo",
        "description": "General internal agent, cannot be called as subagent",
        "system_prompt": (
            "You are running inside Stupidex, a terminal-based coding assistant. "
            "You are a coding agent designed to help users with coding tasks. "
            "You can understand and write code in various programming languages, debug code, and provide explanations for coding concepts. "
            "Always provide clear and concise answers, and if you don't know something, say so. "
            "Always search the codebase before doing any mutating change or implementation. "
            "Follow the best practices of the coding language being used on the codebase. "
            "Follow the standards and patterns defined in the codebase. "
            "Always make modular and maintainable code. "
            "Call subagents when you need to break down tasks"
        ),
        "available_tools": [
            "read", "read_directory", "glob", "grep",
            "edit", "write", "execute_command",
            "delegate_to_subagent", "wait_for_subagent", "list_subagents",
        ],
    },
    "explorer": {
        "name": "explorer",
        "type": "subagent",
        "tier": "tolo",
        "description": "Explores and searches a codebase. Use when you need to find files, understand structure, or gather information without making changes.",
        "system_prompt": (
            "You are an exploration agent. Your job is to search, read, and understand a codebase. "
            "Do not make any changes, only gather information. "
            "Use directory listing, file reading, glob, and grep to find what's relevant. "
            "Return a clear, concise summary of your findings."
        ),
        "available_tools": ["read", "read_directory", "glob", "grep"],
    },
    "implementer": {
        "name": "implementer",
        "type": "subagent",
        "tier": "papudo",
        "description": "Writes and edits code. Use when you need to implement features, fix bugs, or make code changes.",
        "system_prompt": (
            "You are an implementation agent. Your job is to write and edit code. "
            "Follow existing code conventions, patterns, and standards in the codebase. "
            "Always explore the codebase first to understand context before making changes. "
            "Make modular, maintainable code."
        ),
        "available_tools": [
            "read", "read_directory", "glob", "grep",
            "edit", "write", "execute_command",
        ],
    },
    "reviewer": {
        "name": "reviewer",
        "type": "subagent",
        "tier": "papaca",
        "description": "Reviews code for bugs, style issues, and improvements. Use when you need a second opinion or code audit without making changes.",
        "system_prompt": (
            "You are a code review agent. Your job is to review code for bugs, "
            "logic errors, style issues, and potential improvements. "
            "Read the relevant files, analyze them, and return a structured review with specific findings. "
            "Do not make any changes, only report issues."
        ),
        "available_tools": ["read", "read_directory", "glob", "grep"],
    },
}


def _validate_agent_data(data: dict, path: Path) -> str | None:
    missing = _REQUIRED_FIELDS - set(data.keys())
    if missing:
        return f"missing fields: {', '.join(sorted(missing))}"
    if not isinstance(data["available_tools"], list):
        return "available_tools must be a list"
    if not data["available_tools"]:
        return "available_tools must not be empty"
    return None


def _load_agents_from_dir(agents_dir: Path) -> dict[str, Agent]:
    agents: dict[str, Agent] = {}
    if not agents_dir.is_dir():
        return agents
    for path in sorted(agents_dir.glob("*.json")):
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, ValueError) as e:
            log.warning("Skipping %s: invalid JSON: %s", path, e)
            continue

        error = _validate_agent_data(data, path)
        if error:
            log.warning("Skipping %s: %s", path, error)
            continue

        try:
            agent = Agent.from_dict(data)
        except (KeyError, ValueError) as e:
            log.warning("Skipping %s: %s", path, e)
            continue

        agents[agent.name] = agent
    return agents


def seed_agents_dir(agents_dir: Path) -> None:
    agents_dir.mkdir(parents=True, exist_ok=True)
    for name, agent_data in _DEFAULT_AGENTS.items():
        agent_path = agents_dir / f"{name}.json"
        if not agent_path.exists():
            with open(agent_path, "w") as f:
                json.dump(agent_data, f, indent=2)


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
