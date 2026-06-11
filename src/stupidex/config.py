import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

HOME_CONFIG_DIR = Path.home() / ".stupidex"
HOME_CONFIG_PATH = HOME_CONFIG_DIR / "config.json"
HOME_AGENTS_DIR = HOME_CONFIG_DIR / "agents"
PROJECT_CONFIG_NAME = ".stupidex.json"
PROJECT_AGENTS_DIR = ".stupidex/agents"
ENV_PREFIX = "STUPIDEX_"

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


@dataclass
class Config:
    base_url: str = "https://opencode.ai/zen/go/v1"
    default_model: str = "mimo-v2.5"
    provider_api_type: str = "openai"
    tier_models: dict[str, str] = field(default_factory=lambda: {
        "tolo": "mimo-v2.5",
        "tainha": "mimo-v2.5",
        "papudo": "mimo-v2.5",
        "papaca": "mimo-v2.5",
    })
    ignored_dirs: list[str] = field(default_factory=lambda: [
        ".git", ".svn", ".hg",
        "node_modules", "__pycache__",
        "venv", ".venv", "env",
        "dist", "build", "target",
        ".idea", ".vscode", ".vs",
        ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".nox",
        ".eggs", "*.egg-info",
    ])
    command_timeout: int = 30
    read_line_limit: int = 100
    grep_max_results: int = 100
    directory_tree_depth: int = 2


_ENV_MAP = {
    "STUPIDEX_BASE_URL": "base_url",
    "STUPIDEX_DEFAULT_MODEL": "default_model",
    "STUPIDEX_PROVIDER_API_TYPE": "provider_api_type",
    "STUPIDEX_IGNORED_DIRS": "ignored_dirs",
    "STUPIDEX_COMMAND_TIMEOUT": "command_timeout",
    "STUPIDEX_READ_LINE_LIMIT": "read_line_limit",
    "STUPIDEX_GREP_MAX_RESULTS": "grep_max_results",
    "STUPIDEX_DIRECTORY_TREE_DEPTH": "directory_tree_depth",
}


def _load_json(path: Path) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _cast_value(value: str, target_type):
    if target_type is bool:
        return value.lower() in ("true", "1", "yes")
    if target_type is int:
        return int(value)
    if target_type is list:
        return [s.strip() for s in value.split(",")]
    return value


def _merge_from_env(cfg: Config) -> Config:
    values = asdict(cfg)
    for env_key, field_name in _ENV_MAP.items():
        raw = os.environ.get(env_key)
        if raw is not None:
            target_type = type(values[field_name])
            values[field_name] = _cast_value(raw, target_type)
    return Config(**values)


def _seed_agents_dir(agents_dir: Path) -> None:
    agents_dir.mkdir(parents=True, exist_ok=True)
    for name, agent_data in _DEFAULT_AGENTS.items():
        agent_path = agents_dir / f"{name}.json"
        if not agent_path.exists():
            with open(agent_path, "w") as f:
                json.dump(agent_data, f, indent=2)


class ConfigManager:
    _instance: Config | None = None

    @classmethod
    def load(cls) -> Config:
        if cls._instance is not None:
            return cls._instance

        defaults = Config()
        merged = asdict(defaults)

        home = _load_json(HOME_CONFIG_PATH)
        for k, v in home.items():
            if k in merged:
                merged[k] = v

        project_path = Path.cwd() / PROJECT_CONFIG_NAME
        project = _load_json(project_path)
        for k, v in project.items():
            if k in merged:
                merged[k] = v

        cfg = Config(**merged)
        cfg = _merge_from_env(cfg)

        cls._instance = cfg
        return cfg

    @classmethod
    def ensure_home_config(cls) -> None:
        HOME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if not HOME_CONFIG_PATH.exists():
            defaults = Config()
            with open(HOME_CONFIG_PATH, "w") as f:
                json.dump(asdict(defaults), f, indent=2)
        _seed_agents_dir(HOME_AGENTS_DIR)

    @classmethod
    def reset(cls) -> None:
        cls._instance = None


def get_config() -> Config:
    return ConfigManager.load()


def get_model_for_tier(tier: str) -> str:
    cfg = get_config()
    return cfg.tier_models.get(tier, cfg.default_model)
