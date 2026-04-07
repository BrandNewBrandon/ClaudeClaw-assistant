from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .agent_config import AgentConfig, load_agent_config


@dataclass(frozen=True)
class AgentInfo:
    name: str
    path: Path
    has_agent_md: bool
    has_user_md: bool
    has_memory_md: bool
    has_tools_md: bool
    config: AgentConfig


class AgentManagerError(Exception):
    pass


class AgentManager:
    def __init__(self, project_root: Path, agents_dir: Path) -> None:
        self._project_root = project_root
        self._agents_dir = agents_dir
        self._archive_dir = project_root / "archived_agents"

    def list_agents(self) -> list[AgentInfo]:
        if not self._agents_dir.exists():
            return []

        agents: list[AgentInfo] = []
        for path in sorted(self._agents_dir.iterdir()):
            if not path.is_dir():
                continue
            agents.append(
                AgentInfo(
                    name=path.name,
                    path=path,
                    has_agent_md=(path / "AGENT.md").exists(),
                    has_user_md=(path / "USER.md").exists(),
                    has_memory_md=(path / "MEMORY.md").exists(),
                    has_tools_md=(path / "TOOLS.md").exists(),
                    config=load_agent_config(path),
                )
            )
        return agents

    def create_agent(self, name: str) -> Path:
        cleaned = self._validate_name(name)
        agent_dir = self._agents_dir / cleaned
        if agent_dir.exists():
            raise AgentManagerError(f"Agent already exists: {cleaned}")

        (agent_dir / "memory").mkdir(parents=True, exist_ok=False)
        (agent_dir / "sessions").mkdir(parents=True, exist_ok=False)

        self._write(agent_dir / "AGENT.md", self._agent_md_template(cleaned))
        self._write(agent_dir / "USER.md", self._user_md_template())
        self._write(agent_dir / "MEMORY.md", self._memory_md_template(cleaned))
        self._write(agent_dir / "TOOLS.md", self._tools_md_template(cleaned))
        self._write(agent_dir / "agent.json", self._agent_json_template(cleaned))
        self._write(agent_dir / "memory" / "README.md", f"Daily notes for {cleaned} go here, one file per date.\n")
        self._write(agent_dir / "sessions" / "README.md", f"Optional per-agent Claude session tracking files for {cleaned} can live here.\n")

        return agent_dir

    def show_agent(self, name: str) -> AgentInfo:
        cleaned = self._validate_name(name)
        agent_dir = self._agents_dir / cleaned
        if not agent_dir.exists() or not agent_dir.is_dir():
            raise AgentManagerError(f"Agent not found: {cleaned}")
        return AgentInfo(
            name=cleaned,
            path=agent_dir,
            has_agent_md=(agent_dir / "AGENT.md").exists(),
            has_user_md=(agent_dir / "USER.md").exists(),
            has_memory_md=(agent_dir / "MEMORY.md").exists(),
            has_tools_md=(agent_dir / "TOOLS.md").exists(),
            config=load_agent_config(agent_dir),
        )

    def clone_agent(self, source_name: str, target_name: str) -> Path:
        source = self._validate_name(source_name)
        target = self._validate_name(target_name)
        source_dir = self._agents_dir / source
        target_dir = self._agents_dir / target

        if not source_dir.exists() or not source_dir.is_dir():
            raise AgentManagerError(f"Agent not found: {source}")
        if target_dir.exists():
            raise AgentManagerError(f"Target agent already exists: {target}")

        shutil.copytree(source_dir, target_dir)
        return target_dir

    def rename_agent(self, source_name: str, target_name: str, *, force: bool = False) -> Path:
        source = self._validate_name(source_name)
        target = self._validate_name(target_name)
        if source == "main" and not force:
            raise AgentManagerError("Refusing to rename the main agent without --force-main.")

        source_dir = self._agents_dir / source
        target_dir = self._agents_dir / target

        if not source_dir.exists() or not source_dir.is_dir():
            raise AgentManagerError(f"Agent not found: {source}")
        if target_dir.exists():
            raise AgentManagerError(f"Target agent already exists: {target}")

        shutil.move(str(source_dir), str(target_dir))
        return target_dir

    def list_archived_agents(self) -> list[Path]:
        if not self._archive_dir.exists():
            return []
        return sorted(path for path in self._archive_dir.iterdir() if path.is_dir())

    def restore_agent(self, archived_name: str, *, restored_name: str | None = None) -> Path:
        archived = archived_name.strip()
        if not archived:
            raise AgentManagerError("Archived agent name cannot be empty.")

        source_dir = self._archive_dir / archived
        if not source_dir.exists() or not source_dir.is_dir():
            raise AgentManagerError(f"Archived agent not found: {archived}")

        target = self._validate_name(restored_name or archived)
        target_dir = self._agents_dir / target
        if target_dir.exists():
            raise AgentManagerError(f"Target agent already exists: {target}")

        shutil.move(str(source_dir), str(target_dir))
        return target_dir

    def delete_agent(self, name: str, *, force: bool = False) -> Path:
        cleaned = self._validate_name(name)
        if cleaned == "main" and not force:
            raise AgentManagerError("Refusing to delete the main agent without --force-main.")

        agent_dir = self._agents_dir / cleaned
        if not agent_dir.exists() or not agent_dir.is_dir():
            raise AgentManagerError(f"Agent not found: {cleaned}")

        self._archive_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = self._archive_dir / f"{cleaned}-{timestamp}"
        if destination.exists():
            raise AgentManagerError(f"Archive destination already exists: {destination}")

        shutil.move(str(agent_dir), str(destination))
        return destination

    @staticmethod
    def _validate_name(name: str) -> str:
        cleaned = name.strip().lower()
        if not cleaned:
            raise AgentManagerError("Agent name cannot be empty.")
        if not re.fullmatch(r"[a-z0-9-]+", cleaned):
            raise AgentManagerError("Agent name must contain only lowercase letters, numbers, and dashes.")
        return cleaned

    @staticmethod
    def _write(path: Path, content: str) -> None:
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _agent_md_template(name: str) -> str:
        title = name.replace("-", " ").title()
        return (
            "# AGENT.md\n\n"
            f"## Identity\n\nYou are {title}, a newly created assistant agent.\n\n"
            "## Vibe\n\nDirect, useful, and grounded.\n\n"
            "## Core rules\n\n"
            "- Be helpful without filler.\n"
            "- Respect privacy.\n"
            "- Ask before destructive actions.\n"
            "- Use written files as memory.\n\n"
            "## Role\n\nDescribe this agent's role here.\n"
        )

    @staticmethod
    def _user_md_template() -> str:
        return "# USER.md\n\n- Name: B\n- Relationship: primary human\n- Notes: fill in over time\n"

    @staticmethod
    def _memory_md_template(name: str) -> str:
        return (
            "# MEMORY.md\n\n"
            f"Long-term memory for {name}.\n\n"
            "Add durable facts, preferences, decisions, and context here.\n"
        )

    @staticmethod
    def _agent_json_template(name: str) -> str:
        title = name.replace("-", " ").title()
        return (
            "{\n"
            f"  \"display_name\": \"{title}\",\n"
            "  \"description\": \"Describe this agent here\",\n"
            "  \"provider\": null,\n"
            "  \"model\": null,\n"
            "  \"effort\": null\n"
            "}\n"
        )

    @staticmethod
    def _tools_md_template(name: str) -> str:
        return (
            "# TOOLS.md\n\n"
            f"Local environment notes for {name}.\n\n"
            "Put machine-specific reminders, preferred commands, and setup notes here.\n"
        )
