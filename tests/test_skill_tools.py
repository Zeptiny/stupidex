"""Tests for resolve_skill_dependencies (P1-16)."""

import pytest

from stupidex.domain.skill import Skill
from stupidex.tools.skill import resolve_skill_dependencies


def _skill(name: str, requires: list[str] | None = None) -> Skill:
    return Skill(
        name=name,
        description=f"skill {name}",
        location=f"/skills/{name}/SKILL.md",
        content=f"content-{name}",
        requires=list(requires or []),
    )


def _registry(*skills: Skill) -> dict[str, Skill]:
    return {s.name: s for s in skills}


def test_diamond_resolves_without_false_positive():
    """Diamond A->B,C; B->D; C->D resolves without raising; D appears once."""
    registry = _registry(
        _skill("a", ["b", "c"]),
        _skill("b", ["d"]),
        _skill("c", ["d"]),
        _skill("d"),
    )
    result = resolve_skill_dependencies("a", registry, ["*"])
    names = [s.name for s in result]
    assert names.count("d") == 1
    assert "d" in names
    assert "b" in names
    assert "c" in names
    assert "a" in names
    # A must come last (dependents after dependencies).
    assert names.index("d") < names.index("b")
    assert names.index("d") < names.index("c")
    assert names.index("b") < names.index("a")
    assert names.index("c") < names.index("a")


def test_true_cycle_raises():
    """A->B->A raises ValueError."""
    registry = _registry(
        _skill("a", ["b"]),
        _skill("b", ["a"]),
    )
    with pytest.raises(ValueError, match="Circular dependency"):
        resolve_skill_dependencies("a", registry, ["*"])


def test_self_dependency_raises():
    """A->A raises ValueError."""
    registry = _registry(_skill("a", ["a"]))
    with pytest.raises(ValueError, match="Circular dependency"):
        resolve_skill_dependencies("a", registry, ["*"])


def test_linear_chain_resolves_deepest_first():
    """A->B->C->D resolves in dependency order (deepest first)."""
    registry = _registry(
        _skill("a", ["b"]),
        _skill("b", ["c"]),
        _skill("c", ["d"]),
        _skill("d"),
    )
    result = resolve_skill_dependencies("a", registry, ["*"])
    names = [s.name for s in result]
    assert names == ["d", "c", "b", "a"]


def test_sibling_sharing_no_false_positive():
    """A->B,C; B->D,E; C->E — E appears once, no false positive."""
    registry = _registry(
        _skill("a", ["b", "c"]),
        _skill("b", ["d", "e"]),
        _skill("c", ["e"]),
        _skill("d"),
        _skill("e"),
    )
    result = resolve_skill_dependencies("a", registry, ["*"])
    names = [s.name for s in result]
    assert names.count("e") == 1
    assert names.index("e") < names.index("b")
    assert names.index("e") < names.index("c")
    assert names[-1] == "a"
