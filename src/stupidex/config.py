import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

HOME_CONFIG_DIR = Path.home() / ".stupidex"
HOME_CONFIG_PATH = HOME_CONFIG_DIR / "config.json"
HOME_AGENTS_DIR = HOME_CONFIG_DIR / "agents"
HOME_SKILLS_DIR = HOME_CONFIG_DIR / "skills"
PROJECT_CONFIG_NAME = ".stupidex.json"
PROJECT_AGENTS_DIR = ".stupidex/agents"
PROJECT_SKILLS_DIR = ".stupidex/skills"
PROJECT_RAG_DIR = ".stupidex/rag"
RAG_VECTORS_FILE = "vectors.npy"
RAG_INDEX_DB = "index.db"
ENV_PREFIX = "STUPIDEX_"


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
    read_line_limit: int = 1000
    grep_max_results: int = 100
    directory_tree_depth: int = 2
    theme: str = "default"
    personality: str = "default"
    rag_embedding_model: str = ""
    rag_chunk_size: int = 2000
    rag_chunk_overlap: int = 200
    rag_top_k: int = 5
    rag_max_file_size: int = 512000


_ENV_MAP = {
    "STUPIDEX_BASE_URL": "base_url",
    "STUPIDEX_DEFAULT_MODEL": "default_model",
    "STUPIDEX_PROVIDER_API_TYPE": "provider_api_type",
    "STUPIDEX_IGNORED_DIRS": "ignored_dirs",
    "STUPIDEX_COMMAND_TIMEOUT": "command_timeout",
    "STUPIDEX_READ_LINE_LIMIT": "read_line_limit",
    "STUPIDEX_GREP_MAX_RESULTS": "grep_max_results",
    "STUPIDEX_DIRECTORY_TREE_DEPTH": "directory_tree_depth",
    "STUPIDEX_THEME": "theme",
    "STUPIDEX_PERSONALITY": "personality",
    "STUPIDEX_RAG_EMBEDDING_MODEL": "rag_embedding_model",
    "STUPIDEX_RAG_CHUNK_SIZE": "rag_chunk_size",
    "STUPIDEX_RAG_CHUNK_OVERLAP": "rag_chunk_overlap",
    "STUPIDEX_RAG_TOP_K": "rag_top_k",
    "STUPIDEX_RAG_MAX_FILE_SIZE": "rag_max_file_size",
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


_NON_EMPTY_STRINGS = {"base_url", "default_model", "provider_api_type"}


def _validate_config(cfg: Config) -> Config:
    defaults = Config()
    values = asdict(cfg)
    for field_name in _NON_EMPTY_STRINGS:
        val = values.get(field_name)
        if not val or not isinstance(val, str):
            values[field_name] = asdict(defaults)[field_name]

    if values["rag_chunk_size"] <= 0:
        values["rag_chunk_size"] = defaults.rag_chunk_size
    if values["rag_chunk_overlap"] < 0 or values["rag_chunk_overlap"] >= values["rag_chunk_size"]:
        values["rag_chunk_overlap"] = min(defaults.rag_chunk_overlap, values["rag_chunk_size"] - 1)
    if values["rag_top_k"] <= 0:
        values["rag_top_k"] = defaults.rag_top_k
    if values["rag_max_file_size"] <= 0:
        values["rag_max_file_size"] = defaults.rag_max_file_size

    return Config(**values)


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
        cfg = _validate_config(cfg)

        cls._instance = cfg
        return cfg

    @classmethod
    def ensure_home_config(cls) -> None:
        HOME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(str(HOME_CONFIG_DIR), 0o700)
        if not HOME_CONFIG_PATH.exists():
            defaults = Config()
            with open(HOME_CONFIG_PATH, "w") as f:
                json.dump(asdict(defaults), f, indent=2)
            os.chmod(str(HOME_CONFIG_PATH), 0o600)
        from stupidex.agents import load_agents, seed_agents_dir
        seed_agents_dir(HOME_AGENTS_DIR)
        load_agents()
        from stupidex.skills import load_skills, seed_skills_dir
        seed_skills_dir(HOME_SKILLS_DIR)
        load_skills()
        from stupidex.personality import load_personalities
        load_personalities()

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    @classmethod
    def save(cls) -> None:
        if cls._instance is None:
            return
        HOME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = HOME_CONFIG_PATH.with_suffix(".tmp")
        try:
            with open(tmp, "w") as f:
                json.dump(asdict(cls._instance), f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, HOME_CONFIG_PATH)
            os.chmod(str(HOME_CONFIG_PATH), 0o600)
            dir_fd = os.open(str(HOME_CONFIG_DIR), os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except BaseException:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise


def get_config() -> Config:
    return ConfigManager.load()


def get_model_for_tier(tier: str) -> str:
    cfg = get_config()
    return cfg.tier_models.get(tier, cfg.default_model)


def get_current_theme() -> str:
    return get_config().theme


def set_current_theme(name: str) -> None:
    from stupidex.themes import get_theme_registry
    get_theme_registry().get(name)  # raises ValueError for unknown theme
    cfg = get_config()
    cfg.theme = name
    ConfigManager.save()


def get_current_personality() -> str:
    return get_config().personality


def set_current_personality(name: str) -> None:
    from stupidex.personality import get_personality_registry
    get_personality_registry().get(name)  # raises ValueError for unknown
    cfg = get_config()
    cfg.personality = name
    ConfigManager.save()
