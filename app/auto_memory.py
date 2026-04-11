"""Automatic memory extraction from conversations.

After each exchange, asynchronously asks Claude to extract memorable facts
(personal info, preferences, projects, goals) and saves them to daily notes.

Enabled via ``auto_memory: true`` in config.json. Uses low effort to minimize cost.
"""
from __future__ import annotations

import logging
import threading
from datetime import date
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

_EXTRACT_PROMPT = (
    "Below is a conversation exchange. Extract ONLY information worth "
    "remembering across future conversations: personal facts, preferences, "
    "ongoing projects, important names/dates, or stated goals.\n\n"
    "Be extremely selective — most messages contain nothing worth saving. "
    "Return ONLY a short bullet list of new facts (3 bullets max). "
    "If nothing is worth saving, return exactly: NOTHING\n\n"
    "User: {user_message}\n\n"
    "Assistant: {assistant_message}"
)


def extract_and_save(
    user_message: str,
    assistant_message: str,
    *,
    model_runner: Any,
    working_directory: Path,
    notes_dir: Path,
) -> None:
    """Run memory extraction in a background thread (fire-and-forget)."""
    thread = threading.Thread(
        target=_extract,
        kwargs={
            "user_message": user_message,
            "assistant_message": assistant_message,
            "model_runner": model_runner,
            "working_directory": working_directory,
            "notes_dir": notes_dir,
        },
        name="auto-memory",
        daemon=True,
    )
    thread.start()


def _extract(
    *,
    user_message: str,
    assistant_message: str,
    model_runner: Any,
    working_directory: Path,
    notes_dir: Path,
) -> None:
    """Extract facts and save to daily notes. Runs in background thread."""
    prompt = _EXTRACT_PROMPT.format(
        user_message=user_message[:2000],
        assistant_message=assistant_message[:2000],
    )

    try:
        result = model_runner.run_prompt(
            prompt=prompt,
            working_directory=working_directory,
            effort="low",
        )
        facts = result.stdout.strip()
    except Exception:
        LOGGER.exception("Auto-memory extraction failed")
        return

    if not facts or facts.upper() == "NOTHING":
        return

    today_str = date.today().isoformat()
    notes_dir.mkdir(parents=True, exist_ok=True)
    notes_file = notes_dir / f"{today_str}.md"

    try:
        with notes_file.open("a", encoding="utf-8") as fh:
            fh.write(f"\n## Auto-extracted memories\n{facts}\n")
        LOGGER.info("Auto-memory: saved facts to %s", notes_file.name)
    except OSError:
        LOGGER.exception("Auto-memory: failed to write to %s", notes_file)
