"""Automatic memory extraction from conversations.

After each exchange, asynchronously asks Claude to extract a structured
observation (typed, with facts/concepts/files) and stores it via MemoryStore.

Enabled via ``auto_memory: true`` in config.json. Uses low effort to minimize cost.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .memory import MemoryStore

LOGGER = logging.getLogger(__name__)

_EXTRACT_PROMPT = (
    "Below is a conversation exchange. Extract ONLY information worth "
    "remembering across future conversations.\n\n"
    "Be extremely selective — most messages contain nothing worth saving. "
    "If nothing is worth saving, return exactly: NOTHING\n\n"
    "If there IS something worth saving, return a single JSON object with these fields:\n"
    '  "type": one of "decision", "bugfix", "feature", "refactor", "discovery", "change"\n'
    '  "title": short title (under 60 chars)\n'
    '  "narrative": one sentence describing what happened\n'
    '  "facts": list of concise fact strings (3 max)\n'
    '  "concepts": list of topic tags (3 max)\n\n'
    "Return ONLY the JSON object or the word NOTHING. No other text.\n\n"
    "User: {user_message}\n\n"
    "Assistant: {assistant_message}"
)


def extract_and_save(
    user_message: str,
    assistant_message: str,
    *,
    model_runner: Any,
    working_directory: Path,
    memory_store: MemoryStore,
    agent: str,
) -> None:
    """Run memory extraction in a background thread (fire-and-forget)."""
    thread = threading.Thread(
        target=_extract,
        kwargs={
            "user_message": user_message,
            "assistant_message": assistant_message,
            "model_runner": model_runner,
            "working_directory": working_directory,
            "memory_store": memory_store,
            "agent": agent,
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
    memory_store: MemoryStore,
    agent: str,
) -> None:
    """Extract a structured observation and store it. Runs in background thread."""
    from .observations import Observation, ObservationType

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
        raw = result.stdout.strip()
    except Exception:
        LOGGER.exception("Auto-memory extraction failed")
        return

    if not raw or raw.upper() == "NOTHING":
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        LOGGER.debug("Auto-memory: model returned non-JSON: %s", raw[:200])
        return

    try:
        obs = Observation(
            type=ObservationType(data.get("type", "discovery")),
            title=data.get("title", ""),
            narrative=data.get("narrative", ""),
            facts=data.get("facts", []),
            concepts=data.get("concepts", []),
            files_read=data.get("files_read", []),
            files_modified=data.get("files_modified", []),
        )
    except (ValueError, TypeError) as exc:
        LOGGER.debug("Auto-memory: failed to parse observation: %s", exc)
        return

    if not obs.title:
        return

    stored = memory_store.store_observation(agent, obs)
    if stored:
        LOGGER.info("Auto-memory: stored observation '%s' for agent=%s", obs.title, agent)
    else:
        LOGGER.debug("Auto-memory: duplicate observation '%s' skipped", obs.title)
