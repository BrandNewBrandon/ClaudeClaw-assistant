"""Session compaction — auto-summarize old conversation history.

When the conversation transcript exceeds a configurable token budget,
the oldest messages are summarized into a compact paragraph.  The summary
is stored as a special ``direction="compaction"`` entry in the JSONL
transcript.  The context builder uses the last compaction marker to inject
only a summary + recent messages, keeping the prompt lean.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .memory import TranscriptEntry
from .token_estimate import estimate_tokens

if TYPE_CHECKING:
    from .memory import MemoryStore
    from .model_runner import ModelRunner

LOGGER = logging.getLogger(__name__)

_SUMMARIZE_PROMPT = """\
Summarize this conversation history into a compact paragraph (3-6 sentences).
Preserve: key facts, decisions made, tasks discussed, user preferences expressed,
and any pending or unresolved items.  Be concise — this summary replaces the
detailed messages in the agent's context window.

{previous_summary_section}
[Messages to summarize:]
{messages}
"""


class SessionCompactor:
    """Decides when compaction is needed and calls the model to summarize."""

    def __init__(
        self,
        memory: MemoryStore,
        model_runner: ModelRunner,
        token_budget: int = 12_000,
        trigger_ratio: float = 0.8,
        working_directory: Path = Path("."),
    ) -> None:
        self._memory = memory
        self._model_runner = model_runner
        self._token_budget = token_budget
        self._trigger_ratio = trigger_ratio
        self._working_dir = working_directory

    def maybe_compact(
        self,
        surface: str,
        chat_id: str,
        agent: str,
        *,
        account_id: str = "primary",
    ) -> bool:
        """Check if compaction is needed and perform it.

        Returns True if compaction was performed.
        """
        summary, recent = self._memory.read_transcript_with_compaction(
            surface, chat_id, account_id=account_id, agent_name=agent,
        )

        # Estimate tokens of recent (post-compaction) entries
        total_chars = sum(len(e.message_text) for e in recent)
        estimated_tokens = estimate_tokens("x" * total_chars)

        threshold = int(self._token_budget * self._trigger_ratio)
        if estimated_tokens < threshold:
            return False

        LOGGER.info(
            "Compaction triggered: %d tokens > %d threshold "
            "(surface=%s chat_id=%s agent=%s, %d messages)",
            estimated_tokens, threshold, surface, chat_id, agent, len(recent),
        )

        # Split: summarize the older 60%, keep the recent 40% verbatim
        split_idx = max(1, int(len(recent) * 0.6))
        to_summarize = recent[:split_idx]
        # remaining recent entries stay as-is after the new compaction marker

        # Format messages for the summarization prompt
        msg_lines = []
        for entry in to_summarize:
            speaker = "User" if entry.direction == "in" else "Assistant"
            msg_lines.append(f"{speaker}: {entry.message_text}")
        messages_block = "\n".join(msg_lines)

        previous_section = ""
        if summary:
            previous_section = f"[Previous conversation summary:]\n{summary}\n\n"

        prompt = _SUMMARIZE_PROMPT.format(
            previous_summary_section=previous_section,
            messages=messages_block,
        )

        try:
            result = self._model_runner.run_prompt(
                prompt=prompt,
                working_directory=self._working_dir,
                effort="low",
            )
            new_summary = result.stdout.strip()
        except Exception as exc:
            LOGGER.error("Compaction summarization failed: %s", exc)
            return False

        if not new_summary:
            LOGGER.warning("Compaction produced empty summary, skipping")
            return False

        self._memory.append_compaction_summary(
            surface=surface,
            account_id=account_id,
            chat_id=chat_id,
            agent=agent,
            summary_text=new_summary,
            compacted_count=len(to_summarize),
        )

        LOGGER.info(
            "Compaction complete: summarized %d messages into %d chars",
            len(to_summarize), len(new_summary),
        )
        return True
