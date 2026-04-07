from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..tools import ToolHandler, ToolSpec


class SkillBase:
    """Base class for all ClaudeClaw skills.

    A skill bundles related tools, optional slash commands, and optional
    prompt context into a single installable unit.

    Subclasses should override at minimum ``name`` and ``description``, and at
    least one of ``tools()``, ``commands()``, or ``context_text()``.
    """

    #: Unique machine-readable identifier (snake_case).
    name: str = "unnamed"
    #: Human-readable version string.
    version: str = "1.0"
    #: One-line description shown in /skills output.
    description: str = ""

    # ── Core interface ────────────────────────────────────────────────────────

    def tools(self) -> list[tuple[ToolSpec, ToolHandler]]:
        """Return ``[(spec, handler), …]`` to add to the tool registry."""
        return []

    def commands(self) -> dict[str, Callable[[str], str]]:
        """Return ``{"/prefix": handler}`` for slash command dispatch.

        The handler receives the full command text (e.g. ``"/gh issues owner/repo"``)
        and returns a reply string.
        """
        return {}

    def context_text(self) -> str:
        """Return text to inject into every agent prompt, or empty string."""
        return ""

    def is_available(self) -> bool:
        """Return ``True`` when this skill can operate (deps installed, config present)."""
        return True

    def __repr__(self) -> str:
        status = "available" if self.is_available() else "unavailable"
        return f"<{self.__class__.__name__} name={self.name!r} {status}>"
