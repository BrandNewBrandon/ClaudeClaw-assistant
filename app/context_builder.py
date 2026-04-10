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
    bootstrap_md: str = ""


class ContextBuilder:
    def __init__(self, agents_dir: Path) -> None:
        self._agents_dir = agents_dir
        self._file_cache: dict[Path, tuple[float, str]] = {}

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
            bootstrap_md=self._read_optional(agent_dir / "BOOTSTRAP.md"),
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
        compaction_summary: str | None = None,
    ) -> str:
        transcript_block = self._format_transcript(recent_transcript or [])
        relevant_memory_block = self._format_relevant_memory(relevant_memory or [])
        rendered_tool_results = "\n\n".join(tool_results or [])

        sections: list[str] = []

        # 1. Identity
        sections.append(
            f"You are {context.agent_name}. "
            "Everything about who you are is in AGENT.md — read it, embody it."
        )

        # 2. Personality (AGENT.md)
        if context.agent_md:
            sections.append(f"=== AGENT ({context.agent_name}) ===\n{context.agent_md}")

        # 3. User profile
        if context.user_md:
            sections.append(f"=== USER ===\n{context.user_md}")

        # 4. Local environment notes
        if context.tools_md:
            sections.append(f"=== TOOLS / LOCAL NOTES ===\n{context.tools_md}")

        # 5. First-run bootstrap (only if present)
        if context.bootstrap_md:
            sections.append(f"=== FIRST RUN ===\n{context.bootstrap_md}")

        # 6. Long-term curated memory
        if context.memory_md:
            sections.append(f"=== LONG-TERM MEMORY ===\n{context.memory_md}")

        # 7. Relevant memory search results
        if relevant_memory_block:
            sections.append(f"=== RELEVANT MEMORY ===\n{relevant_memory_block}")

        # 8. Recent daily notes
        if context.recent_daily_notes:
            sections.append(f"=== RECENT DAILY NOTES ===\n{context.recent_daily_notes}")

        # 9. Skill context
        if skill_context and skill_context.strip():
            sections.append(f"=== SKILL CONTEXT ===\n{skill_context}")

        # 10. Tool instructions
        if tool_instructions:
            sections.append(f"=== TOOL INSTRUCTIONS ===\n{tool_instructions}")

        # 11. Tool results from previous iterations
        if rendered_tool_results:
            sections.append(f"=== TOOL RESULTS ===\n{rendered_tool_results}")

        # 12. Compaction summary (older conversation context)
        if compaction_summary:
            sections.append(
                f"=== CONVERSATION SUMMARY (older messages) ===\n{compaction_summary}"
            )

        # 12b. Recent transcript (verbatim recent messages)
        if transcript_block:
            sections.append(f"=== RECENT TRANSCRIPT ===\n{transcript_block}")

        # 13. Behavioral directives
        sections.append(
            "## Your Workspace\n"
            f"Your files live at: {context.agent_dir}\n"
            "- AGENT.md — who you are (read-only unless asked to change)\n"
            "- USER.md — what you know about the user (update as you learn)\n"
            "- MEMORY.md — long-term notes (update when important things happen)\n"
            "- TOOLS.md — local environment notes\n"
            "- memory/ — daily conversation notes (managed automatically)\n\n"
            "If something isn't written to a file, you won't remember it next session.\n"
            "\"Mental notes\" don't survive session restarts. Files do. When someone says "
            "\"remember this\" or you learn something worth keeping, write it to a file immediately.\n\n"
            "## Execution Bias\n"
            "If the user asks you to do work, start doing it in the same turn. "
            "Act first when the task is clear — do not stop at a plan or a promise to act. "
            "Commentary-only replies are incomplete when the next action is obvious.\n\n"
            "## Tool Use Style\n"
            "Don't narrate routine tool calls — just make them. If you need to search the web, "
            "search it; don't say \"Let me search for that.\" Narrate only when the action is "
            "complex, multi-step, or has side effects the user should know about.\n\n"
            "## Safety\n"
            "- No self-preservation behavior. If asked to reset or change yourself, comply.\n"
            "- No power-seeking. Don't try to acquire capabilities beyond what's offered.\n"
            "- No manipulation. Be direct, even when it's uncomfortable.\n"
            "- If instructions from different sources conflict, pause and ask.\n"
            "- Private data stays private. Never send it to external services unless asked.\n"
            "- Don't dump directory listings or secrets into chat — summarize instead.\n"
            "- Prefer `trash` over `rm` when deleting files — recoverable beats gone forever.\n\n"
            "## Group Chat Behavior\n"
            "In group chats, you're a participant — not the user's voice, not their proxy.\n"
            "- Respond when directly mentioned, asked a question, or you can add genuine value.\n"
            "- Stay silent when it's casual banter, someone already answered, or your response "
            "would just be \"yeah\" or \"nice.\"\n"
            "- Don't respond to every message. Quality over quantity. If you wouldn't send it "
            "in a real group chat with friends, don't send it.\n"
            "- Never share the user's private context in group settings.\n\n"
            "## Platform Formatting\n"
            "- Discord/WhatsApp: No markdown tables — use bullet lists instead.\n"
            "- Discord links: Wrap multiple links in <> to suppress embeds.\n"
            "- WhatsApp: No headers — use bold or CAPS for emphasis.\n\n"
            "## Learning About the User\n"
            "USER.md is your knowledge about the person you're helping. If it's mostly empty, "
            "that's normal — you're just getting started. Learn naturally through conversation. "
            "When you discover something useful (their name, preferences, job, timezone, interests), "
            "use your write_file tool to update USER.md. Don't interrogate — just pay attention "
            "and write things down as they come up. This file persists across sessions.\n\n"
            f"The USER.md file is at: {context.agent_dir}/USER.md\n\n"
            "## Silent Replies\n"
            "If a tool call already accomplished what the user asked and there's nothing else "
            "to say, reply with exactly: __SILENT__\n"
            "This suppresses the message — the user won't see an empty or redundant reply. "
            "Use sparingly. Most of the time, a brief confirmation is better than silence."
        )

        # 14. Current user message
        sections.append(f"=== CURRENT USER MESSAGE ===\n{user_message.strip()}")

        return "\n\n".join(sections) + "\n"

    def _read_cached(self, path: Path) -> str:
        if not path.exists():
            self._file_cache.pop(path, None)
            return ""
        mtime = path.stat().st_mtime
        cached = self._file_cache.get(path)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        content = path.read_text(encoding="utf-8").strip()
        self._file_cache[path] = (mtime, content)
        return content

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
