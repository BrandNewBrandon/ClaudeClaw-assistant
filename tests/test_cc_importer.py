"""Tests for Claude Code skill importer."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from app.skills.cc_importer import (
    _parse_skill_name,
    _parse_skill_frontmatter,
    _read_skill_body,
    _find_skill_files,
    _load_agent_cc_skills,
    _save_agent_cc_skills,
    CCImporterSkill,
)


def _create_skill_md(path: Path, name: str, description: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_parse_skill_name(tmp_path: Path) -> None:
    skill_md = tmp_path / "my-skill" / "SKILL.md"
    _create_skill_md(skill_md, "my-skill", "A test skill", "Body text")
    assert _parse_skill_name(skill_md) == "my-skill"


def test_parse_skill_name_fallback_to_dir(tmp_path: Path) -> None:
    skill_md = tmp_path / "fallback-name" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("No frontmatter here", encoding="utf-8")
    assert _parse_skill_name(skill_md) == "fallback-name"


def test_parse_skill_frontmatter(tmp_path: Path) -> None:
    skill_md = tmp_path / "test" / "SKILL.md"
    _create_skill_md(skill_md, "test-skill", "Does testing", "Body")
    fm = _parse_skill_frontmatter(skill_md)
    assert fm["name"] == "test-skill"
    assert fm["description"] == "Does testing"


def test_read_skill_body(tmp_path: Path) -> None:
    skill_md = tmp_path / "test" / "SKILL.md"
    _create_skill_md(skill_md, "test", "desc", "# Instructions\n\nDo the thing.")
    body = _read_skill_body(skill_md)
    assert "# Instructions" in body
    assert "Do the thing" in body
    assert "---" not in body  # Frontmatter stripped


def test_find_skill_files(tmp_path: Path) -> None:
    # Create fake plugin cache
    skill1 = tmp_path / "cache" / "plugin1" / "v1" / "skills" / "my-skill" / "SKILL.md"
    skill2 = tmp_path / "cache" / "plugin2" / "v1" / "skills" / "other-skill" / "SKILL.md"
    _create_skill_md(skill1, "my-skill", "desc1", "body1")
    _create_skill_md(skill2, "other-skill", "desc2", "body2")

    with patch("app.skills.cc_importer._CC_PLUGIN_DIRS", [tmp_path / "cache"]):
        found = _find_skill_files()
    assert "my-skill" in found
    assert "other-skill" in found


def test_load_agent_cc_skills(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)
    (agents_dir / "main" / "agent.json").write_text(
        json.dumps({"cc_skills": ["tdd", "brainstorming"]}), encoding="utf-8",
    )
    result = _load_agent_cc_skills(agents_dir, "main")
    assert result == ["tdd", "brainstorming"]


def test_load_agent_cc_skills_all(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)
    (agents_dir / "main" / "agent.json").write_text(
        json.dumps({"cc_skills": "all"}), encoding="utf-8",
    )
    assert _load_agent_cc_skills(agents_dir, "main") == "all"


def test_load_agent_cc_skills_missing(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)
    assert _load_agent_cc_skills(agents_dir, "main") == []


def test_save_agent_cc_skills(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)
    _save_agent_cc_skills(agents_dir, "main", ["skill-a", "skill-b"])
    data = json.loads((agents_dir / "main" / "agent.json").read_text(encoding="utf-8"))
    assert data["cc_skills"] == ["skill-a", "skill-b"]


def test_save_preserves_existing_fields(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)
    (agents_dir / "main" / "agent.json").write_text(
        json.dumps({"display_name": "Main Agent", "model": "opus"}), encoding="utf-8",
    )
    _save_agent_cc_skills(agents_dir, "main", ["tdd"])
    data = json.loads((agents_dir / "main" / "agent.json").read_text(encoding="utf-8"))
    assert data["display_name"] == "Main Agent"
    assert data["model"] == "opus"
    assert data["cc_skills"] == ["tdd"]


def test_context_text_for_agent(tmp_path: Path) -> None:
    # Create fake plugin
    skill_md = tmp_path / "cache" / "p" / "v" / "skills" / "tdd" / "SKILL.md"
    _create_skill_md(skill_md, "tdd", "Test-driven development", "Write tests first.")

    # Create agent config
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)
    (agents_dir / "main" / "agent.json").write_text(
        json.dumps({"cc_skills": ["tdd"]}), encoding="utf-8",
    )

    with patch("app.skills.cc_importer._CC_PLUGIN_DIRS", [tmp_path / "cache"]):
        skill = CCImporterSkill(agents_dir=agents_dir)
        context = skill.context_text_for_agent("main")

    assert "Write tests first" in context
    assert "Imported Skill: tdd" in context


def test_context_text_for_agent_none_enabled(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)
    skill = CCImporterSkill(agents_dir=agents_dir)
    assert skill.context_text_for_agent("main") == ""


def test_cmd_list(tmp_path: Path) -> None:
    skill_md = tmp_path / "cache" / "p" / "v" / "skills" / "my-skill" / "SKILL.md"
    _create_skill_md(skill_md, "my-skill", "A cool skill", "body")

    with patch("app.skills.cc_importer._CC_PLUGIN_DIRS", [tmp_path / "cache"]):
        skill = CCImporterSkill(agents_dir=tmp_path / "agents")
        result = skill._cmd_list("/cc-skills")

    assert "my-skill" in result
    assert "A cool skill" in result


def test_cmd_import(tmp_path: Path) -> None:
    skill_md = tmp_path / "cache" / "p" / "v" / "skills" / "tdd" / "SKILL.md"
    _create_skill_md(skill_md, "tdd", "TDD skill", "body")

    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)

    with patch("app.skills.cc_importer._CC_PLUGIN_DIRS", [tmp_path / "cache"]):
        skill = CCImporterSkill(agents_dir=agents_dir)
        result = skill._cmd_import("/cc-import tdd")

    assert "tdd" in result
    # Verify it was saved
    data = json.loads((agents_dir / "main" / "agent.json").read_text(encoding="utf-8"))
    assert "tdd" in data["cc_skills"]


def test_cmd_remove(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)
    (agents_dir / "main" / "agent.json").write_text(
        json.dumps({"cc_skills": ["tdd", "brainstorming"]}), encoding="utf-8",
    )

    with patch("app.skills.cc_importer._CC_PLUGIN_DIRS", [tmp_path / "cache"]):
        skill = CCImporterSkill(agents_dir=agents_dir)
        skill._skill_cache = {"tdd": Path("/fake"), "brainstorming": Path("/fake")}
        result = skill._cmd_remove("/cc-remove tdd")

    assert "removed" in result.lower()
    data = json.loads((agents_dir / "main" / "agent.json").read_text(encoding="utf-8"))
    assert "tdd" not in data["cc_skills"]
    assert "brainstorming" in data["cc_skills"]
