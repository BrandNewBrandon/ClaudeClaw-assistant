from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .memory import TranscriptEntry


@dataclass(frozen=True)
class AgentContext:
    agent_name: str
    agent_dir: Path
    agent_md: str
    user_md: str
    memory_md: str
    tools_md: str
    recent_daily_notes: str


class ContextBuilder:
    def __init__(self, agents_dir: Path) -> None:
        self._agents_dir = agents_dir

    def load_agent_context(self, agent_name: str) -> AgentContext:
        agent_dir = self._agents_dir / agent_name
        if not agent_dir.exists():
            raise FileNotFoundError(f"Agent directory not found: {agent_dir}")

        return AgentContext(
            agent_name=agent_name,
            agent_dir=agent_dir,
            agent_md=self._read_optional(agent_dir / "AGENT.md"),
            user_md=self._read_optional(agent_dir / "USER.md"),
            memory_md=self._read_optional(agent_dir / "MEMORY.md"),
            tools_md=self._read_optional(agent_dir / "TOOLS.md"),
            recent_daily_notes=self._load_recent_daily_notes(agent_dir / "memory"),
        )

    def build_prompt(
        self,
        context: AgentContext,
        user_message: str,
        recent_transcript: list[TranscriptEntry] | None = None,
        relevant_memory: list[str] | None = None,
        tool_instructions: str | None = None,
        tool_results: list[str] | None = None,
        skill_context: str | None = None,
    ) -> str:
        transcript_block = self._format_transcript(recent_transcript or [])
        relevant_memory_block = self._format_relevant_memory(relevant_memory or [])
        rendered_tool_results = "\n\n".join(tool_results or [])
        skill_block = f"=== SKILL CONTEXT ===\n{skill_context}\n\n" if skill_context and skill_context.strip() else ""
        return (
            "You are operating inside a personal assistant runtime.\n\n"
            "Follow the agent identity and memory files below.\n"
            "Be direct, useful, and grounded.\n"
            "If you do not know something, say so plainly.\n"
            "Do not invent memories that are not present in the files.\n\n"
            f"=== AGENT ({context.agent_name}) ===\n{context.agent_md}\n\n"
            f"=== USER ===\n{context.user_md}\n\n"
            f"=== LONG-TERM MEMORY ===\n{context.memory_md}\n\n"
            f"=== RELEVANT MEMORY ===\n{relevant_memory_block}\n\n"
            f"=== TOOLS / LOCAL NOTES ===\n{context.tools_md}\n\n"
            f"{skill_block}"
            f"=== TOOL INSTRUCTIONS ===\n{tool_instructions or ''}\n\n"
            f"=== TOOL RESULTS ===\n{rendered_tool_results}\n\n"
            f"=== RECENT DAILY NOTES ===\n{context.recent_daily_notes}\n\n"
            f"=== RECENT TRANSCRIPT ===\n{transcript_block}\n\n"
            "=== CURRENT USER MESSAGE ===\n"
            f"{user_message.strip()}\n\n"
            "Reply to the user naturally. Keep it clear and useful."
        )

    def _load_recent_daily_notes(self, memory_dir: Path) -> str:
        if not memory_dir.exists():
            return ""

        files = sorted(memory_dir.glob("*.md"), reverse=True)
        recent = []
        for path in files:
            if path.name.upper() == "README.MD":
                continue
            recent.append(f"# {path.name}\n{self._read_optional(path)}")
            if len(recent) >= 2:
                break
        return "\n\n".join(recent)

    @staticmethod
    def _format_transcript(entries: list[TranscriptEntry]) -> str:
        if not entries:
            return ""
        lines = []
        for entry in entries:
            speaker = "User" if entry.direction == "in" else "Assistant"
            lines.append(f"[{entry.timestamp}] {speaker}: {entry.message_text}")
        return "\n".join(lines)

    @staticmethod
    def _format_relevant_memory(snippets: list[str]) -> str:
        if not snippets:
            return ""
        return "\n\n".join(f"- {snippet}" for snippet in snippets)

    @staticmethod
    def _read_optional(path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()
