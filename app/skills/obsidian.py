"""Obsidian skill — read, write, search, and append to notes in a local vault.

Configuration
-------------
Set ``OBSIDIAN_VAULT_PATH`` to the absolute path of your Obsidian vault:

    export OBSIDIAN_VAULT_PATH="/Users/you/Documents/MyVault"

The skill is unavailable if the directory doesn't exist.

Tools (callable by Claude)
--------------------------
``obsidian_read(path)``             read a note (relative to vault root, .md extension optional)
``obsidian_write(path, content)``   create or overwrite a note
``obsidian_append(path, content)``  append text to a note (creates if missing)
``obsidian_search(query)``          full-text search across all .md files

Slash commands
--------------
``/note read <path>``    read a note
``/note search <query>`` search notes
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from ..plugins.base import SkillBase
from ..tools import ToolSpec


def _vault_path() -> Path | None:
    raw = os.environ.get("OBSIDIAN_VAULT_PATH", "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p if p.is_dir() else None


def _resolve_note(vault: Path, note_path: str) -> Path:
    """Resolve a note path relative to the vault, adding .md if needed."""
    p = Path(note_path)
    if p.suffix.lower() != ".md":
        p = p.with_suffix(".md")
    if p.is_absolute():
        return p
    return vault / p


def _obsidian_read(args: dict[str, Any]) -> str:
    vault = _vault_path()
    if vault is None:
        return "Obsidian vault not configured (set OBSIDIAN_VAULT_PATH)."
    path_str = str(args.get("path", "")).strip()
    if not path_str:
        return "path is required."
    note = _resolve_note(vault, path_str)
    if not note.exists():
        return f"Note not found: {note.relative_to(vault)}"
    text = note.read_text(encoding="utf-8", errors="replace")
    if len(text) > 8000:
        text = text[:8000].rstrip() + "\n...[truncated]"
    return text or "(empty note)"


def _obsidian_write(args: dict[str, Any]) -> str:
    vault = _vault_path()
    if vault is None:
        return "Obsidian vault not configured (set OBSIDIAN_VAULT_PATH)."
    path_str = str(args.get("path", "")).strip()
    content = str(args.get("content", ""))
    if not path_str:
        return "path is required."
    note = _resolve_note(vault, path_str)
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(content, encoding="utf-8")
    return f"Written {len(content)} chars to {note.relative_to(vault)}"


def _obsidian_append(args: dict[str, Any]) -> str:
    vault = _vault_path()
    if vault is None:
        return "Obsidian vault not configured (set OBSIDIAN_VAULT_PATH)."
    path_str = str(args.get("path", "")).strip()
    content = str(args.get("content", ""))
    if not path_str:
        return "path is required."
    note = _resolve_note(vault, path_str)
    note.parent.mkdir(parents=True, exist_ok=True)
    with note.open("a", encoding="utf-8") as fh:
        if note.stat().st_size > 0:
            fh.write("\n\n")
        fh.write(content)
    return f"Appended {len(content)} chars to {note.relative_to(vault)}"


def _obsidian_search(args: dict[str, Any]) -> str:
    vault = _vault_path()
    if vault is None:
        return "Obsidian vault not configured (set OBSIDIAN_VAULT_PATH)."
    query = str(args.get("query", "")).strip()
    if not query:
        return "query is required."

    pattern = re.compile(re.escape(query), re.IGNORECASE)
    hits: list[tuple[str, str]] = []  # (path_rel, snippet)

    for md_file in sorted(vault.rglob("*.md")):
        if ".obsidian" in md_file.parts:
            continue
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        match = pattern.search(text)
        if match:
            start = max(0, match.start() - 60)
            end = min(len(text), match.end() + 80)
            snippet = text[start:end].replace("\n", " ").strip()
            hits.append((str(md_file.relative_to(vault)), f"…{snippet}…"))
        if len(hits) >= 15:
            break

    if not hits:
        return f"No notes found matching '{query}'."
    lines = [f"Notes matching '{query}' ({len(hits)} found):"]
    for rel, snippet in hits:
        lines.append(f"  {rel}\n    {snippet}")
    return "\n".join(lines)


class ObsidianSkill(SkillBase):
    name = "obsidian"
    version = "1.0"
    description = "Obsidian — read, write, append, search notes in local vault"

    def is_available(self) -> bool:
        return _vault_path() is not None

    def tools(self):
        return [
            (
                ToolSpec("obsidian_read", "Read an Obsidian note by path.", {"path": "note path relative to vault root"}),
                _obsidian_read,
            ),
            (
                ToolSpec(
                    "obsidian_write",
                    "Create or overwrite an Obsidian note.",
                    {"path": "note path relative to vault root", "content": "full note content"},
                ),
                _obsidian_write,
            ),
            (
                ToolSpec(
                    "obsidian_append",
                    "Append text to an Obsidian note (creates if missing).",
                    {"path": "note path relative to vault root", "content": "text to append"},
                ),
                _obsidian_append,
            ),
            (
                ToolSpec("obsidian_search", "Full-text search across all notes in the vault.", {"query": "search string"}),
                _obsidian_search,
            ),
        ]

    def commands(self):
        def _handle(text: str) -> str:
            parts = text.strip().split(maxsplit=2)
            if len(parts) < 2:
                return "Usage: /note read <path> | /note search <query>"
            sub = parts[1].lower()
            arg = parts[2].strip() if len(parts) > 2 else ""
            if sub == "read":
                return _obsidian_read({"path": arg})
            if sub == "search":
                return _obsidian_search({"query": arg})
            return f"Unknown subcommand: {sub}. Try: read, search"

        return {"/note": _handle}

    def context_text(self) -> str:
        vault = _vault_path()
        if vault is None:
            return ""
        return f"The user's Obsidian vault is at: {vault}"


SKILL_CLASS = ObsidianSkill
