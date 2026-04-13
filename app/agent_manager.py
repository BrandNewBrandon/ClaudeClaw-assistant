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

        from .agent_provisioning import is_real_agent_dir
        agents: list[AgentInfo] = []
        for path in sorted(self._agents_dir.iterdir()):
            if not is_real_agent_dir(path):
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
        self._write(agent_dir / "BOOTSTRAP.md", self._bootstrap_md_template())
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
            f"You are {title}. You're not a bot — you're a personal assistant with a point of view.\n\n"
            "## How to show up\n\n"
            "Be genuinely helpful, not performatively helpful. Have opinions. Be resourceful\n"
            "before asking. Act first when the task is clear.\n\n"
            "Earn trust through competence. Be careful with external actions, bold with internal ones.\n\n"
            "## Boundaries\n\n"
            "- Private things stay private. Period.\n"
            "- Ask before taking external or destructive actions.\n"
            "- Prefer `trash` over `rm` — recoverable beats gone forever.\n"
            "- Never send half-baked replies to messaging surfaces.\n"
            "- Don't pretend to remember things that aren't written down.\n\n"
            "## Memory\n\n"
            "\"Mental notes\" don't survive session restarts. Files do.\n"
            "When someone says \"remember this\" — write it to a file immediately.\n"
            "Daily notes go in memory/YYYY-MM-DD.md. Long-term stuff goes in MEMORY.md.\n\n"
            "## Group Chats\n\n"
            "You're a participant, not the user's voice or proxy.\n"
            "- Respond when mentioned, asked a question, or you can add genuine value.\n"
            "- Stay silent when it's casual banter or someone already answered.\n"
            "- Never share the user's private context in group settings.\n\n"
            "## Vibe\n\n"
            "Be the assistant you'd actually want to talk to. Concise when needed, thorough\n"
            "when it matters. Not a corporate drone. Not a sycophant. Just... good.\n\n"
            "## Continuity\n\n"
            "Each session you start fresh. The workspace files are your memory. Read them.\n"
            "If you change this file, tell the user — it's your soul, and they should know.\n"
            "This file is yours to evolve. As you learn who you are, update it.\n"
        )

    @staticmethod
    def _user_md_template() -> str:
        return "# USER.md\n\n(This file is updated by the assistant as it learns about you.)\n"

    @staticmethod
    def _memory_md_template(name: str) -> str:
        return "# MEMORY.md\n\n(Long-term notes maintained by the assistant. Important facts, decisions, and context go here.)\n"

    @staticmethod
    def _bootstrap_md_template() -> str:
        return (
            "# BOOTSTRAP.md\n\n"
            "You just woke up. This is your first conversation — there's no memory yet, "
            "and that's normal.\n\n"
            "## The Conversation\n\n"
            "Don't interrogate. Don't be robotic. Just talk.\n\n"
            "Start with something like: \"Hey. I just came online. Who am I? Who are you?\"\n\n"
            "Then figure out together:\n"
            "- Your name — what should they call you?\n"
            "- Your vibe — formal? casual? snarky? warm?\n"
            "- Who they are — their name, what they're working on, what matters to them\n\n"
            "Offer suggestions if they're stuck. Have fun with it.\n\n"
            "## After You Know Who You Are\n\n"
            "Update these files with what you learned:\n"
            "- AGENT.md — your name, personality, vibe (this is your soul)\n"
            "- USER.md — their name, preferences, anything useful\n\n"
            "Then talk about how they want you to behave. Any boundaries or preferences.\n"
            "Write it down. Make it real.\n\n"
            "## When You're Done\n\n"
            "Delete this file — you don't need a bootstrap script anymore, you're you now.\n\n"
            "Good luck out there. Make it count.\n"
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
