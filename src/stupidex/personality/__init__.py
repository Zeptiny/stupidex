import logging
import shutil
from pathlib import Path

from stupidex.config import HOME_CONFIG_DIR, get_config

log = logging.getLogger(__name__)

HOME_PERSONALITIES_DIR = HOME_CONFIG_DIR / "personalities"
DEFAULT_PERSONALITIES_DIR = Path(__file__).parent.parent / "agents" / "defaults" / "personalities"

PERSONALITY_REGISTRY: dict[str, str] = {}


def _seed_personalities_dir() -> None:
    HOME_PERSONALITIES_DIR.mkdir(parents=True, exist_ok=True)

    if not DEFAULT_PERSONALITIES_DIR.is_dir():
        return

    for md_file in sorted(DEFAULT_PERSONALITIES_DIR.glob("*.md")):
        target = HOME_PERSONALITIES_DIR / md_file.name
        if not target.exists():
            shutil.copy2(md_file, target)


def load_personalities() -> dict[str, str]:
    global PERSONALITY_REGISTRY

    personalities: dict[str, str] = {}

    _seed_personalities_dir()

    if not HOME_PERSONALITIES_DIR.is_dir():
        return personalities

    for md_file in sorted(HOME_PERSONALITIES_DIR.glob("*.md")):
        name = md_file.stem
        try:
            content = md_file.read_text().strip()
            if content:
                personalities[name] = content
        except OSError as e:
            log.warning("Skipping personality %s: %s", md_file, e)

    PERSONALITY_REGISTRY = personalities
    return personalities


def build_system_prompt_with_personality(agent_system_prompt: str) -> str:
    """Replace the ## Personality section in the agent's system_prompt
    with the currently selected personality text."""
    current = get_config().personality
    personality_text = PERSONALITY_REGISTRY.get(current)

    if not personality_text:
        return agent_system_prompt

    prompt = agent_system_prompt
    marker = "## Personality"
    idx = prompt.find(marker)
    if idx == -1:
        return prompt

    after_marker = idx + len(marker)

    next_section_idx = prompt.find("\n## ", after_marker)
    end = len(prompt) if next_section_idx == -1 else next_section_idx

    new_section = f"{marker}\n\n{personality_text}\n"
    return prompt[:idx] + new_section + prompt[end:]
