from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .base import SkillBase
from ..tools import ToolRegistry, build_default_registry

if TYPE_CHECKING:
    pass

LOGGER = logging.getLogger(__name__)


class PluginRegistry:
    """Aggregates all loaded skills and provides unified access to their
    tools, commands, and context contributions."""

    def __init__(self, skills: list[SkillBase]) -> None:
        self._all_skills = list(skills)
        self._available: list[SkillBase] = []
        for skill in self._all_skills:
            try:
                if skill.is_available():
                    self._available.append(skill)
                    LOGGER.info("Skill loaded: %s v%s", skill.name, skill.version)
                else:
                    LOGGER.debug("Skill unavailable (missing deps/config): %s", skill.name)
            except Exception:
                LOGGER.exception("Error checking skill availability: %s", skill.name)

    # ── Skills access ─────────────────────────────────────────────────────────

    @property
    def all_skills(self) -> list[SkillBase]:
        return list(self._all_skills)

    @property
    def available_skills(self) -> list[SkillBase]:
        return list(self._available)

    # ── Tools ─────────────────────────────────────────────────────────────────

    def build_tool_registry(self, working_directory: str | Path | None = None) -> ToolRegistry:
        """Build a ToolRegistry containing built-in tools plus all skill tools."""
        registry = build_default_registry(working_directory)
        for skill in self._available:
            try:
                for spec, handler in skill.tools():
                    registry.register(spec, handler)
            except Exception:
                LOGGER.exception("Failed to register tools for skill: %s", skill.name)
        return registry

    # ── Commands ──────────────────────────────────────────────────────────────

    def handle_command(self, text: str) -> str | None:
        """Dispatch a slash command to a matching skill.

        Returns a reply string if a skill handles the command, else ``None``.
        """
        stripped = text.strip()
        for skill in self._available:
            try:
                for prefix, handler in skill.commands().items():
                    if stripped == prefix or stripped.startswith(prefix + " "):
                        return handler(stripped)
            except Exception:
                LOGGER.exception("Skill command handler error: %s", skill.name)
        return None

    # ── Context ───────────────────────────────────────────────────────────────

    def get_context_text(self) -> str:
        """Combine all skill context injections into a single string."""
        parts: list[str] = []
        for skill in self._available:
            try:
                text = skill.context_text()
                if text and text.strip():
                    parts.append(text.strip())
            except Exception:
                LOGGER.exception("Skill context_text error: %s", skill.name)
        return "\n\n".join(parts)

    def get_relevant_context_text(self, message: str, *, agent_name: str | None = None) -> str:
        """Only include skill context for skills whose summary keywords match the message.

        Falls back to full context if no skills match (so nothing is lost).
        If ``agent_name`` is provided, also includes agent-specific context
        from skills that support it (e.g., imported Claude Code skills).
        """
        lowered = message.lower()
        relevant: list[str] = []
        for skill in self._available:
            try:
                # Agent-specific context (CC importer)
                if agent_name and hasattr(skill, "context_text_for_agent"):
                    agent_text = skill.context_text_for_agent(agent_name)
                    if agent_text and agent_text.strip():
                        relevant.append(agent_text.strip())
                        continue  # Don't also add generic context_text

                keywords = skill.summary.lower().split()
                if not keywords:
                    # No summary defined — always include
                    text = skill.context_text()
                    if text and text.strip():
                        relevant.append(text.strip())
                    continue
                if any(kw in lowered for kw in keywords):
                    text = skill.context_text()
                    if text and text.strip():
                        relevant.append(text.strip())
            except Exception:
                LOGGER.exception("Skill context_text error: %s", skill.name)
        # Fallback: if keyword filtering produced nothing, include all
        if not relevant:
            return self.get_context_text()
        return "\n\n".join(relevant)

    # ── Status ────────────────────────────────────────────────────────────────

    def status_lines(self) -> list[str]:
        """Human-readable status list for /skills command."""
        lines: list[str] = []
        for skill in self._all_skills:
            available = "✓" if skill in self._available else "✗"
            lines.append(f"{available} {skill.name} v{skill.version} — {skill.description}")
        return lines
