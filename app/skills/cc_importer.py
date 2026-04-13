"""Claude Code skill importer — auto-converts CC skill files into ClaudeClaw skills.

Scans ~/.claude/plugins/ and ~/.assistant/cc-skills/ for Claude Code skills
(SKILL.md files), reads their markdown content, and exposes them as ClaudeClaw
skills via context_text() injection.

Configuration
-------------
Set ``cc_skills`` in agent.json to control which CC skills are imported:

    {"cc_skills": ["brainstorming", "test-driven-development"]}

Or set to ``"all"`` to import everything:

    {"cc_skills": "all"}

If not set, no CC skills are imported (opt-in).

Slash commands
--------------
``/cc-skills``                list available Claude Code skills
``/cc-skill <name>``          show details about a specific CC skill
``/cc-import <name>``         add a CC skill to the current agent's cc_skills list
``/cc-remove <name>``         remove a CC skill from the current agent's cc_skills list
``/cc-install <github-url>``  install a CC skill/plugin from GitHub
``/cc-uninstall <name>``      remove an installed CC skill/plugin
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

from ..plugins.base import SkillBase

LOGGER = logging.getLogger(__name__)

# Where user-installed CC skills are stored
_USER_CC_SKILLS_DIR = Path.home() / ".assistant" / "cc-skills"

# Standard locations for Claude Code plugins
_CC_PLUGIN_DIRS = [
    Path.home() / ".claude" / "plugins" / "cache",
    _USER_CC_SKILLS_DIR,
]


def _find_skill_files() -> dict[str, Path]:
    """Discover all SKILL.md files in Claude Code plugin directories.

    Returns {skill_name: path_to_SKILL.md}.
    """
    skills: dict[str, Path] = {}
    for plugin_dir in _CC_PLUGIN_DIRS:
        if not plugin_dir.exists():
            continue
        for skill_md in sorted(plugin_dir.rglob("SKILL.md")):
            name = _parse_skill_name(skill_md)
            if name and name not in skills:
                skills[name] = skill_md
    return skills


def _parse_skill_name(path: Path) -> str | None:
    """Extract skill name from SKILL.md frontmatter."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None

    # Parse YAML frontmatter
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return path.parent.name  # Fall back to directory name

    frontmatter = match.group(1)
    for line in frontmatter.splitlines():
        line = line.strip()
        if line.startswith("name:"):
            name = line[5:].strip().strip("'\"")
            return name or None

    return path.parent.name


def _parse_skill_frontmatter(path: Path) -> dict[str, str]:
    """Parse frontmatter from a SKILL.md file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}

    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {"name": path.parent.name}

    result: dict[str, str] = {}
    frontmatter = match.group(1)
    current_key: str | None = None
    current_value_lines: list[str] = []

    for line in frontmatter.splitlines():
        # Check for new key
        key_match = re.match(r"^(\w+):\s*(.*)", line)
        if key_match:
            # Save previous key
            if current_key:
                result[current_key] = " ".join(current_value_lines).strip().strip("'\"")
            current_key = key_match.group(1)
            value = key_match.group(2).strip()
            if value == ">" or value == "|":
                current_value_lines = []
            else:
                current_value_lines = [value.strip("'\"")]
        elif current_key and line.strip():
            current_value_lines.append(line.strip())

    if current_key:
        result[current_key] = " ".join(current_value_lines).strip().strip("'\"")

    return result


def _read_skill_body(path: Path) -> str:
    """Read the body content (after frontmatter) from a SKILL.md file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""

    # Strip frontmatter
    match = re.match(r"^---\s*\n.*?\n---\s*\n?", text, re.DOTALL)
    if match:
        return text[match.end():].strip()
    return text.strip()


def _load_agent_cc_skills(agents_dir: Path, agent_name: str) -> list[str] | str:
    """Load the cc_skills setting from agent.json.

    Returns list of skill names, "all", or empty list.
    """
    agent_json = agents_dir / agent_name / "agent.json"
    if not agent_json.exists():
        return []
    try:
        data = json.loads(agent_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    cc_skills = data.get("cc_skills")
    if cc_skills == "all":
        return "all"
    if isinstance(cc_skills, list):
        return [str(s).strip() for s in cc_skills if str(s).strip()]
    return []


def _save_agent_cc_skills(agents_dir: Path, agent_name: str, cc_skills: list[str] | str) -> None:
    """Save the cc_skills setting to agent.json."""
    agent_json = agents_dir / agent_name / "agent.json"
    data: dict[str, Any] = {}
    if agent_json.exists():
        try:
            data = json.loads(agent_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    data["cc_skills"] = cc_skills
    agent_json.parent.mkdir(parents=True, exist_ok=True)
    agent_json.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _install_from_github(url: str) -> tuple[str, str]:
    """Install a CC skill/plugin from a GitHub URL.

    Clones the repo into ~/.assistant/cc-skills/<repo-name>/.
    Returns (repo_name, message).
    """
    # Normalize URL
    url = url.strip().rstrip("/")
    if not url.startswith(("http://", "https://", "git@")):
        # Assume shorthand: "user/repo"
        if "/" in url and not url.startswith("/"):
            url = f"https://github.com/{url}"
        else:
            raise ValueError(f"Invalid URL or shorthand: {url}. Use 'owner/repo' or full GitHub URL.")

    # Extract repo name from URL
    repo_name = url.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    if not repo_name:
        raise ValueError(f"Cannot determine repo name from URL: {url}")

    dest = _USER_CC_SKILLS_DIR / repo_name
    if dest.exists():
        raise ValueError(f"Already installed: {repo_name}. Use /cc-uninstall {repo_name} first.")

    _USER_CC_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    # Try git clone first
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(dest)],
            capture_output=True, text=True, timeout=60,
            creationflags=(subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0),  # type: ignore[attr-defined]
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "git clone failed")
    except FileNotFoundError:
        raise ValueError("git is not installed. Install git to use /cc-install.")
    except subprocess.TimeoutExpired:
        # Clean up partial clone
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        raise ValueError("git clone timed out after 60 seconds.")

    # Verify it has skill files
    skill_files = list(dest.rglob("SKILL.md"))
    if not skill_files:
        # Not a CC plugin — clean up
        shutil.rmtree(dest, ignore_errors=True)
        raise ValueError(f"No SKILL.md files found in {url}. Not a valid Claude Code plugin.")

    skill_names = []
    for sf in skill_files:
        name = _parse_skill_name(sf)
        if name:
            skill_names.append(name)

    return repo_name, f"Installed {repo_name} with {len(skill_names)} skill(s): {', '.join(skill_names)}"


def _uninstall_skill(name: str) -> str:
    """Remove an installed CC skill/plugin by repo name."""
    dest = _USER_CC_SKILLS_DIR / name
    if not dest.exists():
        raise ValueError(f"Not installed: {name}")
    shutil.rmtree(dest)
    return f"Uninstalled {name}."


class CCImporterSkill(SkillBase):
    """Imports Claude Code skills into ClaudeClaw."""

    name = "cc_importer"
    version = "1.1"
    description = "Import Claude Code skills — /cc-skills to list, /cc-install to add from GitHub"

    def __init__(self, agents_dir: Path | None = None) -> None:
        self._agents_dir = agents_dir
        self._skill_cache: dict[str, Path] | None = None

    def _discover(self) -> dict[str, Path]:
        if self._skill_cache is None:
            self._skill_cache = _find_skill_files()
        return self._skill_cache

    def is_available(self) -> bool:
        return bool(self._discover())

    def tools(self):
        return []  # No tools — context injection only

    def commands(self) -> dict[str, Callable[[str], str]]:
        return {
            "/cc-skills": self._cmd_list,
            "/cc-skill": self._cmd_detail,
            "/cc-import": self._cmd_import,
            "/cc-remove": self._cmd_remove,
            "/cc-install": self._cmd_install,
            "/cc-uninstall": self._cmd_uninstall,
        }

    def context_text(self) -> str:
        """Return empty — use context_text_for_agent() instead."""
        return ""

    def context_text_for_agent(self, agent_name: str) -> str:
        """Return merged CC skill content for a specific agent."""
        if self._agents_dir is None:
            return ""

        enabled = _load_agent_cc_skills(self._agents_dir, agent_name)
        if not enabled:
            return ""

        available = self._discover()
        if enabled == "all":
            names = sorted(available.keys())
        else:
            names = [n for n in enabled if n in available]

        if not names:
            return ""

        sections: list[str] = []
        for skill_name in names:
            path = available[skill_name]
            body = _read_skill_body(path)
            if body:
                sections.append(f"## [Imported Skill: {skill_name}]\n\n{body}")

        if not sections:
            return ""

        return (
            "# Claude Code Skills (imported)\n\n"
            "The following skill instructions have been imported from Claude Code plugins. "
            "Follow their guidance when relevant.\n\n"
            + "\n\n---\n\n".join(sections)
        )

    # ── Commands ─────────────────────────────────────────────────────────────

    def _cmd_list(self, text: str) -> str:
        available = self._discover()
        if not available:
            return "No Claude Code skills found in ~/.claude/plugins/"

        # Show which are enabled for current agent
        enabled: list[str] | str = []
        if self._agents_dir:
            # We don't have agent_name here — just list all available
            pass

        lines = [f"Claude Code skills available ({len(available)}):"]
        for name, path in sorted(available.items()):
            fm = _parse_skill_frontmatter(path)
            desc = fm.get("description", "")[:80]
            lines.append(f"  {name} — {desc}")
        lines.append("")
        lines.append("Use /cc-import <name> to add a skill to your agent.")
        return "\n".join(lines)

    def _cmd_detail(self, text: str) -> str:
        parts = text.strip().split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            return "Usage: /cc-skill <name>"
        skill_name = parts[1].strip()
        available = self._discover()
        if skill_name not in available:
            return f"Skill not found: {skill_name}. Use /cc-skills to list available skills."
        path = available[skill_name]
        fm = _parse_skill_frontmatter(path)
        body = _read_skill_body(path)
        lines = [
            f"Skill: {skill_name}",
            f"Description: {fm.get('description', '(none)')}",
            f"Source: {path}",
            f"Content length: {len(body)} chars",
            "",
            "Preview (first 500 chars):",
            body[:500],
        ]
        return "\n".join(lines)

    def _cmd_import(self, text: str) -> str:
        parts = text.strip().split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            return "Usage: /cc-import <name> or /cc-import all"
        skill_name = parts[1].strip()

        if self._agents_dir is None:
            return "Cannot import — agents directory not configured."

        available = self._discover()

        if skill_name == "all":
            # Import everything — find current agent from context
            return self._import_for_agent("all", available)

        if skill_name not in available:
            return f"Skill not found: {skill_name}. Use /cc-skills to list available skills."

        return self._import_for_agent(skill_name, available)

    def _import_for_agent(self, skill_name: str, available: dict[str, Path]) -> str:
        """Import a skill into the agent's cc_skills list.

        Note: we need the agent name from the command context, but commands()
        don't receive it. We'll write to all agents that have a cc_skills field,
        or to the default agent directory.
        """
        if self._agents_dir is None:
            return "Cannot import — agents directory not configured."

        # Find agents that exist
        agents = [d.name for d in self._agents_dir.iterdir() if d.is_dir() and not d.name.startswith((".", "_"))]
        if not agents:
            return "No agents found."

        # For simplicity, ask user to specify or default to first agent
        if skill_name == "all":
            for agent in agents:
                _save_agent_cc_skills(self._agents_dir, agent, "all")
            return f"All Claude Code skills enabled for: {', '.join(agents)}"

        results: list[str] = []
        for agent in agents:
            current = _load_agent_cc_skills(self._agents_dir, agent)
            if current == "all":
                results.append(f"  {agent}: already set to 'all'")
                continue
            if isinstance(current, list):
                if skill_name not in current:
                    current.append(skill_name)
                    _save_agent_cc_skills(self._agents_dir, agent, current)
                    results.append(f"  {agent}: added {skill_name}")
                else:
                    results.append(f"  {agent}: already has {skill_name}")

        return f"Imported '{skill_name}':\n" + "\n".join(results)

    def _cmd_remove(self, text: str) -> str:
        parts = text.strip().split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            return "Usage: /cc-remove <name>"
        skill_name = parts[1].strip()

        if self._agents_dir is None:
            return "Cannot remove — agents directory not configured."

        agents = [d.name for d in self._agents_dir.iterdir() if d.is_dir() and not d.name.startswith((".", "_"))]
        results: list[str] = []
        for agent in agents:
            current = _load_agent_cc_skills(self._agents_dir, agent)
            if current == "all":
                # Convert "all" to explicit list minus the removed skill
                all_names = list(self._discover().keys())
                new_list = [n for n in all_names if n != skill_name]
                _save_agent_cc_skills(self._agents_dir, agent, new_list)
                results.append(f"  {agent}: removed {skill_name} (converted from 'all' to explicit list)")
            elif isinstance(current, list) and skill_name in current:
                current.remove(skill_name)
                _save_agent_cc_skills(self._agents_dir, agent, current)
                results.append(f"  {agent}: removed {skill_name}")

        if not results:
            return f"Skill '{skill_name}' not found in any agent's cc_skills."
        return f"Removed '{skill_name}':\n" + "\n".join(results)

    def _cmd_install(self, text: str) -> str:
        parts = text.strip().split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            return (
                "Usage: /cc-install <github-url>\n"
                "Examples:\n"
                "  /cc-install owner/repo\n"
                "  /cc-install https://github.com/owner/repo"
            )
        url = parts[1].strip()
        try:
            repo_name, message = _install_from_github(url)
            # Invalidate cache so new skills appear immediately
            self._skill_cache = None
            return message
        except ValueError as exc:
            return f"Install failed: {exc}"
        except Exception as exc:
            return f"Install failed: {exc}"

    def _cmd_uninstall(self, text: str) -> str:
        parts = text.strip().split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            # List installed repos
            if not _USER_CC_SKILLS_DIR.exists():
                return "No skills installed. Use /cc-install <github-url> to install."
            installed = [d.name for d in sorted(_USER_CC_SKILLS_DIR.iterdir()) if d.is_dir()]
            if not installed:
                return "No skills installed. Use /cc-install <github-url> to install."
            return (
                "Usage: /cc-uninstall <name>\n"
                f"Installed: {', '.join(installed)}"
            )
        name = parts[1].strip()
        try:
            message = _uninstall_skill(name)
            # Invalidate cache
            self._skill_cache = None
            return message
        except ValueError as exc:
            return str(exc)


SKILL_CLASS = CCImporterSkill
