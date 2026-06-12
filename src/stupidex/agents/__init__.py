import logging
import re
from pathlib import Path

from stupidex.config import HOME_AGENTS_DIR, PROJECT_AGENTS_DIR
from stupidex.domain.agent import Agent, AgentTypes, ModelTier

log = logging.getLogger(__name__)

AGENT_REGISTRY: dict[str, Agent] = {}

_FRONTMATTER_PATTERN = re.compile(
    r'^---\s*\n(.*?)\n---\s*\n(.*)',
    re.DOTALL
)


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content.

    Returns (metadata_dict, body_content).
    """
    match = _FRONTMATTER_PATTERN.match(content.strip())
    if not match:
        return {}, content

    frontmatter_str = match.group(1)
    body = match.group(2)

    metadata = {}
    current_key = None
    current_list = None

    for line in frontmatter_str.split('\n'):
        stripped = line.strip()

        # List item under a key
        if stripped.startswith('- ') and current_key:
            if current_list is None:
                current_list = []
            current_list.append(stripped[2:].strip().strip("'\""))
            continue

        # Save previous list if we hit a new key
        if current_list is not None and current_key:
            metadata[current_key] = current_list
            current_list = None

        if not stripped or ':' not in stripped:
            continue

        key, _, value = stripped.partition(':')
        key = key.strip()
        value = value.strip()

        current_key = key

        # Remove quotes if present
        if value and value[0] in ('"', "'") and value[-1] == value[0]:
            value = value[1:-1]

        if value:
            metadata[key] = value
            current_list = None
        else:
            current_list = []

    # Save any trailing list
    if current_list is not None and current_key:
        metadata[current_key] = current_list

    return metadata, body


def _load_agents_from_dir(agents_dir: Path) -> dict[str, Agent]:
    agents: dict[str, Agent] = {}
    if not agents_dir.is_dir():
        return agents

    for path in sorted(agents_dir.iterdir()):
        if not path.is_dir():
            continue

        agent_file = path / "AGENT.md"
        if not agent_file.exists():
            continue

        try:
            content = agent_file.read_text()
        except OSError as e:
            log.warning("Skipping %s: %s", agent_file, e)
            continue

        metadata, body = _parse_frontmatter(content)

        name = metadata.get('name', path.name)
        agent_type = metadata.get('type', 'subagent')
        tier = metadata.get('tier', 'papudo')
        description = metadata.get('description', '')
        available_tools = metadata.get('available_tools', [])

        if not description:
            log.warning("Skipping %s: no description in frontmatter", agent_file)
            continue

        if not available_tools:
            log.warning("Skipping %s: no available_tools in frontmatter", agent_file)
            continue

        if not isinstance(available_tools, list):
            log.warning("Skipping %s: available_tools must be a list", agent_file)
            continue

        try:
            agent = Agent(
                name=name,
                type=AgentTypes.from_str(agent_type),
                tier=ModelTier.from_str(tier),
                description=description,
                system_prompt=body.strip(),
                available_tools=available_tools,
            )
        except (KeyError, ValueError) as e:
            log.warning("Skipping %s: %s", agent_file, e)
            continue

        agents[agent.name] = agent

    return agents


def seed_agents_dir(agents_dir: Path) -> None:
    agents_dir.mkdir(parents=True, exist_ok=True)

    # Get the source defaults directory
    source_agents_dir = Path(__file__).parent / "defaults"

    for source_agent_dir in sorted(source_agents_dir.iterdir()):
        if not source_agent_dir.is_dir():
            continue

        source_agent_file = source_agent_dir / "AGENT.md"
        if not source_agent_file.exists():
            continue

        target_dir = agents_dir / source_agent_dir.name
        target_file = target_dir / "AGENT.md"

        if not target_file.exists():
            import shutil
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_agent_file, target_file)


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
