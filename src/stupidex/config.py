import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

_MCP_SERVER_NAME_RE = re.compile(r"^[a-z0-9-]+$")
_PROVIDER_ALIAS_RE = re.compile(r"^[a-z0-9-]+$")
_PROVIDER_MODEL_OVERRIDE_KEYS = frozenset(
    {"max_input_tokens", "max_output_tokens", "supports_vision", "mode", "litellm_provider"}
)
_RESERVED_PROVIDER_ALIASES = frozenset({"fastembed"})

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
    default_model: str = "default/mimo-v2.5"
    tier_models: dict[str, str] = field(
        default_factory=lambda: {
            "tolo": "default/mimo-v2.5",
            "tainha": "default/mimo-v2.5",
            "papudo": "default/mimo-v2.5",
            "papaca": "default/mimo-v2.5",
        }
    )
    ignored_dirs: list[str] = field(
        default_factory=lambda: [
            ".git",
            ".svn",
            ".hg",
            "node_modules",
            "__pycache__",
            "venv",
            ".venv",
            "env",
            "dist",
            "build",
            "target",
            ".idea",
            ".vscode",
            ".vs",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".tox",
            ".nox",
            ".eggs",
            "*.egg-info",
        ]
    )
    command_timeout: int = 30
    read_line_limit: int = 1000
    grep_max_results: int = 100
    directory_tree_depth: int = 2
    theme: str = "default"
    personality: str = "default"
    rag_embedding_model: str = "fastembed/BAAI/bge-small-en-v1.5"
    rag_chunk_size: int = 2000
    rag_chunk_overlap: int = 200
    rag_top_k: int = 5
    rag_max_file_size: int = 512000
    mcp_servers: dict[str, dict] = field(
        default_factory=lambda: {
            "context7": {
                "command": "npx",
                "args": ["-y", "@upstash/context7-mcp"],
            },
            "example": {
                "command": "python",
                "args": ["-m", "stupidex.mcp.example_server"],
            },
        }
    )
    providers: dict[str, dict] = field(
        default_factory=lambda: {
            "default": {
                "base_url": "https://opencode.ai/zen/go/v1",
                "litellm_provider": "openai",
                "models": {"mimo-v2.5": {}},
            }
        }
    )


_ENV_MAP = {
    "STUPIDEX_DEFAULT_MODEL": "default_model",
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


_NON_EMPTY_STRINGS = {"default_model"}


def _validate_provider_entry(alias: str, entry: object) -> tuple[bool, dict | None]:
    """Validate a single `providers[alias]` entry.

    Mirrors the warn-and-skip pattern used for `mcp_servers`. Returns
    `(keep, cleaned_entry)` — `keep` is False when the entry is dropped
    entirely; `cleaned_entry` is the validated dict to store when kept.
    """
    if not isinstance(entry, dict):
        log.warning(
            "Skipping provider '%s': config must be a dict, got %s",
            alias,
            type(entry).__name__,
        )
        return False, None
    if not _PROVIDER_ALIAS_RE.match(alias):
        log.warning(
            "Skipping provider '%s': alias must match [a-z0-9-]+ (no '/')",
            alias,
        )
        return False, None
    if alias in _RESERVED_PROVIDER_ALIASES:
        log.warning(
            "Skipping provider '%s': alias is reserved (built-in pseudo-provider)",
            alias,
        )
        return False, None

    cleaned: dict = {}

    base_url = entry.get("base_url")
    if base_url is not None:
        if not isinstance(base_url, str) or not base_url:
            log.warning(
                "Provider '%s': 'base_url' must be a non-empty string, got %s; dropping field",
                alias,
                type(base_url).__name__,
            )
        else:
            cleaned["base_url"] = base_url

    api_key = entry.get("api_key")
    api_key_env = entry.get("api_key_env")
    has_api_key = api_key is not None
    has_api_key_env = api_key_env is not None
    if has_api_key:
        if not isinstance(api_key, str) or not api_key:
            log.warning(
                "Provider '%s': 'api_key' must be a non-empty string, got %s; dropping field",
                alias,
                type(api_key).__name__,
            )
            has_api_key = False
        else:
            cleaned["api_key"] = api_key
    if has_api_key_env:
        if not isinstance(api_key_env, str) or not api_key_env:
            log.warning(
                "Provider '%s': 'api_key_env' must be a non-empty string, got %s; dropping field",
                alias,
                type(api_key_env).__name__,
            )
            has_api_key_env = False
        else:
            cleaned["api_key_env"] = api_key_env
    if has_api_key and has_api_key_env:
        log.warning(
            "Provider '%s': both 'api_key' and 'api_key_env' set; dropping 'api_key_env'",
            alias,
        )
        cleaned.pop("api_key_env", None)

    litellm_provider = entry.get("litellm_provider")
    if litellm_provider is not None:
        if not isinstance(litellm_provider, str) or not litellm_provider:
            log.warning(
                "Provider '%s': 'litellm_provider' must be a non-empty string, got %s; dropping field",
                alias,
                type(litellm_provider).__name__,
            )
        else:
            cleaned["litellm_provider"] = litellm_provider

    models = entry.get("models", {})
    if not isinstance(models, dict):
        log.warning(
            "Provider '%s': 'models' must be a dict, got %s; treating as empty",
            alias,
            type(models).__name__,
        )
        models = {}
    cleaned_models: dict[str, dict] = {}
    for model_id, override in models.items():
        if override is None:
            cleaned_models[str(model_id)] = {}
            continue
        if not isinstance(override, dict):
            log.warning(
                "Provider '%s': model '%s' override must be a dict, got %s; treating as empty",
                alias,
                model_id,
                type(override).__name__,
            )
            cleaned_models[str(model_id)] = {}
            continue
        cleaned_override: dict = {}
        for k, v in override.items():
            if k in _PROVIDER_MODEL_OVERRIDE_KEYS:
                cleaned_override[k] = v
            else:
                log.warning(
                    "Provider '%s': model '%s' has unknown override field '%s'; dropping",
                    alias,
                    model_id,
                    k,
                )
        cleaned_models[str(model_id)] = cleaned_override
    cleaned["models"] = cleaned_models

    return True, cleaned


def _validate_config(cfg: Config) -> Config:
    defaults = Config()
    values = asdict(cfg)
    for field_name in _NON_EMPTY_STRINGS:
        val = values.get(field_name)
        if not val or not isinstance(val, str):
            values[field_name] = asdict(defaults)[field_name]

    if not isinstance(values["rag_chunk_size"], int) or values["rag_chunk_size"] <= 0:
        values["rag_chunk_size"] = defaults.rag_chunk_size
    if not isinstance(values["rag_chunk_overlap"], int):
        values["rag_chunk_overlap"] = defaults.rag_chunk_overlap
    elif values["rag_chunk_overlap"] < 0 or values["rag_chunk_overlap"] >= values["rag_chunk_size"]:
        values["rag_chunk_overlap"] = min(defaults.rag_chunk_overlap, values["rag_chunk_size"] - 1)
    if not isinstance(values["rag_top_k"], int) or values["rag_top_k"] <= 0:
        values["rag_top_k"] = defaults.rag_top_k
    if not isinstance(values["rag_max_file_size"], int) or values["rag_max_file_size"] <= 0:
        values["rag_max_file_size"] = defaults.rag_max_file_size

    mcp_servers = values.get("mcp_servers", {})
    if not isinstance(mcp_servers, dict):
        mcp_servers = {}
    cleaned_mcp: dict[str, dict] = {}
    for name, server_cfg in mcp_servers.items():
        if not isinstance(server_cfg, dict):
            log.warning("Skipping MCP server '%s': config must be a dict, got %s", name, type(server_cfg).__name__)
            continue
        if not _MCP_SERVER_NAME_RE.match(name):
            log.warning("Skipping MCP server '%s': name must match [a-z0-9-]+", name)
            continue
        if "url" not in server_cfg:
            cmd = server_cfg.get("command")
            if not isinstance(cmd, str):
                log.warning("Skipping MCP server '%s': 'command' must be a string, got %s", name, type(cmd).__name__)
                continue
            args = server_cfg.get("args", [])
            if not isinstance(args, list):
                log.warning("Skipping MCP server '%s': 'args' must be a list, got %s", name, type(args).__name__)
                continue
        cleaned_mcp[name] = server_cfg
    values["mcp_servers"] = cleaned_mcp

    providers = values.get("providers", {})
    if not isinstance(providers, dict):
        log.warning("'providers' must be a dict, got %s; resetting to empty", type(providers).__name__)
        providers = {}
    cleaned_providers: dict[str, dict] = {}
    for alias, entry in providers.items():
        keep, cleaned = _validate_provider_entry(alias, entry)
        if keep and cleaned is not None:
            cleaned_providers[alias] = cleaned
    values["providers"] = cleaned_providers

    return Config(**values)


def _deep_merge_provider_dict(home: dict, project: dict) -> dict:
    """Recursively merge two provider-dict-shaped values (`providers` or `mcp_servers`).

    For each alias present in either side:
    - present only in `home` → take home entry;
    - present only in `project` → take project entry;
    - present in both as dicts → entry fields shallow-merge as `{**home_entry,
      **project_entry}`, with a recursive merge of a nested `models` sub-dict
      when both sides carry one (preserves home-only fields when project adds
      a new model).

    Anything other than a dict on either side falls back to the project value
    (matches the prior `mcp_servers` merge behavior).
    """
    result: dict[str, dict] = {}
    for alias in set(home) | set(project):
        if alias not in project:
            result[alias] = home[alias]
            continue
        if alias not in home:
            result[alias] = project[alias]
            continue
        home_entry = home[alias]
        project_entry = project[alias]
        if not isinstance(home_entry, dict) or not isinstance(project_entry, dict):
            result[alias] = project_entry
            continue
        merged_entry = {**home_entry, **project_entry}
        home_models = home_entry.get("models")
        project_models = project_entry.get("models")
        if isinstance(home_models, dict) and isinstance(project_models, dict):
            merged_entry["models"] = {**home_models, **project_models}
        result[alias] = merged_entry
    return result


_DEEP_MERGE_KEYS = frozenset({"mcp_servers", "providers"})


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
            if k not in merged:
                continue
            if k in _DEEP_MERGE_KEYS and isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = _deep_merge_provider_dict(merged[k], v)
            else:
                merged[k] = v

        project_path = Path.cwd() / PROJECT_CONFIG_NAME
        project = _load_json(project_path)
        for k, v in project.items():
            if k not in merged:
                continue
            if k in _DEEP_MERGE_KEYS and isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = _deep_merge_provider_dict(merged[k], v)
            else:
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
