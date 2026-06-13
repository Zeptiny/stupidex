import logging
from pathlib import Path

from stupidex.config import HOME_SKILLS_DIR, PROJECT_SKILLS_DIR
from stupidex.domain.skill import Skill
from stupidex.utils import parse_frontmatter, seed_defaults

log = logging.getLogger(__name__)

SKILL_REGISTRY: dict[str, Skill] = {}


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

        metadata, body = parse_frontmatter(content)

        name = metadata.get("name", path.name)
        description = metadata.get("description", "")

        if not description:
            log.warning("Skipping %s: no description in frontmatter", skill_file)
            continue

        skill = Skill(
            name=name,
            description=description,
            location=str(skill_file),
            content=body.strip(),
        )
        skills[name] = skill

    return skills


def seed_skills_dir(skills_dir: Path) -> None:
    source_dir = Path(__file__).parent / "defaults"
    seed_defaults(source_dir, skills_dir, "SKILL.md")


def load_skills() -> dict[str, Skill]:
    global SKILL_REGISTRY

    home_skills = _load_skills_from_dir(HOME_SKILLS_DIR)

    project_skills_dir = Path.cwd() / PROJECT_SKILLS_DIR
    project_skills = _load_skills_from_dir(project_skills_dir)

    merged = {**home_skills, **project_skills}
    SKILL_REGISTRY = merged

    from stupidex.tools import reset_tool_registry
    reset_tool_registry()

    return merged


def get_skill_registry() -> dict[str, Skill]:
    if not SKILL_REGISTRY:
        return load_skills()
    return SKILL_REGISTRY
