import logging
import re
from pathlib import Path

from stupidex.config import HOME_SKILLS_DIR, PROJECT_SKILLS_DIR
from stupidex.domain.skill import Skill

log = logging.getLogger(__name__)

SKILL_REGISTRY: dict[str, Skill] = {}

_FRONTMATTER_PATTERN = re.compile(
    r'^---\s*\n(.*?)\n---\s*\n(.*)',
    re.DOTALL
)


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content.

    Returns (metadata_dict, body_content).
    If no frontmatter is found, returns ({}, content).
    """
    match = _FRONTMATTER_PATTERN.match(content.strip())
    if not match:
        return {}, content

    frontmatter_str = match.group(1)
    body = match.group(2)

    metadata = {}
    for line in frontmatter_str.split('\n'):
        line = line.strip()
        if not line or ':' not in line:
            continue

        key, _, value = line.partition(':')
        key = key.strip()
        value = value.strip()

        # Remove quotes if present
        if value and value[0] in ('"', "'") and value[-1] == value[0]:
            value = value[1:-1]

        metadata[key] = value

    return metadata, body


def _load_skills_from_dir(skills_dir: Path) -> dict[str, Skill]:
    skills: dict[str, Skill] = {}
    if not skills_dir.is_dir():
        return skills

    for path in sorted(skills_dir.iterdir()):
        if not path.is_dir():
            continue

        skill_file = path / "SKILL.md"
        if not skill_file.exists():
            continue

        try:
            content = skill_file.read_text()
        except OSError as e:
            log.warning("Skipping %s: %s", skill_file, e)
            continue

        metadata, body = _parse_frontmatter(content)

        name = metadata.get('name', path.name)

        description = metadata.get('description', '')
        if not description:
            log.warning("Skipping %s: no description in frontmatter", skill_file)
            continue

        skill = Skill(
            name=name,
            description=description,
            location=str(skill_file),
            content=body.strip() if body.strip() else content,
        )
        skills[name] = skill

    return skills


def seed_skills_dir(skills_dir: Path) -> None:
    skills_dir.mkdir(parents=True, exist_ok=True)

    # Get the source defaults directory (where the default skills are)
    source_skills_dir = Path(__file__).parent / "defaults"

    # Copy all skill directories from source
    for source_skill_dir in sorted(source_skills_dir.iterdir()):
        if not source_skill_dir.is_dir():
            continue

        source_skill_file = source_skill_dir / "SKILL.md"
        if not source_skill_file.exists():
            continue

        target_dir = skills_dir / source_skill_dir.name
        target_file = target_dir / "SKILL.md"

        if not target_file.exists():
            import shutil
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_skill_file, target_file)


def load_skills() -> dict[str, Skill]:
    global SKILL_REGISTRY

    home_skills = _load_skills_from_dir(HOME_SKILLS_DIR)

    project_skills_dir = Path.cwd() / PROJECT_SKILLS_DIR
    project_skills = _load_skills_from_dir(project_skills_dir)

    merged = {**home_skills, **project_skills}
    SKILL_REGISTRY = merged
    return merged


def get_skill_registry() -> dict[str, Skill]:
    if not SKILL_REGISTRY:
        return load_skills()
    return SKILL_REGISTRY


def get_skill(name: str) -> Skill | None:
    registry = get_skill_registry()
    return registry.get(name)
