from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .model_runner import ModelRunner

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscriptEntry:
    timestamp: str
    surface: str
    account_id: str
    chat_id: str
    direction: str
    agent: str
    message_text: str
    metadata: dict[str, Any]


class MemoryStore:
    def __init__(self, shared_dir: Path, agents_dir: Path) -> None:
        self._shared_dir = shared_dir
        self._agents_dir = agents_dir

    def long_term_memory_path(self, agent: str) -> Path:
        return self._agents_dir / agent / "MEMORY.md"

    def read_long_term_memory(self, agent: str) -> str:
        path = self.long_term_memory_path(agent)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()

    def find_relevant_memory(self, agent: str, query: str, *, limit: int = 4) -> list[str]:
        query_terms = self._keyword_terms(query)
        if not query_terms:
            return []

        candidates: list[tuple[int, str]] = []
        for source_text in self._memory_sources(agent):
            for snippet in self._split_snippets(source_text):
                lowered = snippet.lower()
                score = sum(1 for term in query_terms if term in lowered)
                if score > 0:
                    candidates.append((score, snippet))

        candidates.sort(key=lambda item: (-item[0], len(item[1])))
        seen: set[str] = set()
        results: list[str] = []
        for _score, snippet in candidates:
            if snippet in seen:
                continue
            seen.add(snippet)
            results.append(snippet)
            if len(results) >= limit:
                break
        return results

    def transcript_path(self, surface: str, chat_id: str, *, account_id: str = "primary") -> Path:
        return self._shared_dir / "transcripts" / f"{surface}-{account_id}-{chat_id}.jsonl"

    def append_transcript(
        self,
        *,
        surface: str,
        account_id: str = "primary",
        chat_id: str,
        direction: str,
        agent: str,
        message_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        transcript_dir = self._shared_dir / "transcripts"
        transcript_dir.mkdir(parents=True, exist_ok=True)
        path = self.transcript_path(surface, chat_id, account_id=account_id)

        entry = TranscriptEntry(
            timestamp=self._now_iso(),
            surface=surface,
            account_id=account_id,
            chat_id=chat_id,
            direction=direction,
            agent=agent,
            message_text=message_text,
            metadata=metadata or {},
        )

        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")

    def read_recent_transcript(self, surface: str, chat_id: str, limit: int = 6, *, account_id: str = "primary") -> list[TranscriptEntry]:
        path = self.transcript_path(surface, chat_id, account_id=account_id)
        if not path.exists():
            return []

        lines = path.read_text(encoding="utf-8").splitlines()
        entries: list[TranscriptEntry] = []
        for line in lines[-limit:]:
            if not line.strip():
                continue
            raw = json.loads(line)
            entries.append(
                TranscriptEntry(
                    timestamp=str(raw.get("timestamp", "")),
                    surface=str(raw.get("surface", "")),
                    account_id=str(raw.get("account_id", "primary")),
                    chat_id=str(raw.get("chat_id", "")),
                    direction=str(raw.get("direction", "")),
                    agent=str(raw.get("agent", "")),
                    message_text=str(raw.get("message_text", "")),
                    metadata=raw.get("metadata", {}) or {},
                )
            )
        return entries

    def consolidate_agent_notes(
        self,
        agent: str,
        model_runner: ModelRunner,
        working_directory: Path,
        *,
        keep_days: int = 3,
        model: str | None = None,
        effort: str | None = None,
    ) -> str:
        """Consolidate daily notes older than keep_days into MEMORY.md.

        Returns a human-readable summary of what was done.
        """
        memory_dir = self._daily_notes_dir(agent)
        if not memory_dir.exists():
            return "No daily notes directory found."

        cutoff_date = (datetime.now().astimezone() - timedelta(days=keep_days)).date()
        old_files: list[Path] = []
        for path in sorted(memory_dir.glob("*.md")):
            if path.name.upper() == "README.MD":
                continue
            parsed = _parse_date_from_stem(path.stem)
            if parsed is not None and parsed < cutoff_date:
                old_files.append(path)

        if not old_files:
            return f"No notes older than {keep_days} days to consolidate."

        combined_text = "\n\n---\n\n".join(
            f"# {path.stem}\n{path.read_text(encoding='utf-8').strip()}"
            for path in old_files
        )

        prompt = (
            f"The following are daily conversation notes for agent '{agent}'. "
            "Extract the key facts, decisions, preferences, and important information that should be "
            "remembered long-term. Return ONLY a compact markdown bullet list of facts — "
            "no preamble, no dates, no timestamps. Each bullet should be a concise, standalone fact.\n\n"
            f"{combined_text}"
        )

        try:
            result = model_runner.run_prompt(
                prompt=prompt,
                working_directory=working_directory,
                model=model,
                effort=effort or "low",
            )
            extracted = result.stdout.strip()
        except Exception as exc:
            return f"Consolidation failed: {exc}"

        if not extracted:
            return "No facts extracted from notes."

        memory_path = self.long_term_memory_path(agent)
        memory_path.parent.mkdir(parents=True, exist_ok=True)
        with memory_path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n\n## Consolidated {self._now_human()}\n{extracted}\n")

        archive_dir = memory_dir / "archived"
        archive_dir.mkdir(exist_ok=True)
        for path in old_files:
            path.rename(archive_dir / path.name)

        return (
            f"Consolidated {len(old_files)} daily note(s) into MEMORY.md "
            f"and archived originals to {archive_dir.name}/."
        )

    def append_daily_note(self, agent: str, note: str) -> Path:
        note = note.strip()
        agent_memory_dir = self._daily_notes_dir(agent)
        agent_memory_dir.mkdir(parents=True, exist_ok=True)
        path = agent_memory_dir / f"{self._today_string()}.md"

        with path.open("a", encoding="utf-8") as handle:
            if path.exists() and path.stat().st_size > 0:
                handle.write("\n\n")
            handle.write(f"## {self._now_human()}\n{note}\n")

        return path

    def _daily_notes_dir(self, agent: str) -> Path:
        return self._agents_dir / agent / "memory"

    def _memory_sources(self, agent: str) -> list[str]:
        sources: list[str] = []
        long_term_memory = self.read_long_term_memory(agent)
        if long_term_memory:
            sources.append(long_term_memory)

        memory_dir = self._daily_notes_dir(agent)
        if memory_dir.exists():
            for path in sorted(memory_dir.glob("*.md"), reverse=True)[:3]:
                if path.name.upper() == "README.MD":
                    continue
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    sources.append(content)
        return sources

    @staticmethod
    def _split_snippets(text: str) -> list[str]:
        parts = [part.strip() for part in re.split(r"\n\s*\n|\n(?=#|[-*])", text) if part.strip()]
        return parts

    @staticmethod
    def _keyword_terms(text: str) -> list[str]:
        terms = [term.lower() for term in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", text)]
        stop_words = {
            "what",
            "when",
            "where",
            "which",
            "with",
            "that",
            "this",
            "have",
            "from",
            "your",
            "about",
            "they",
            "them",
            "into",
            "were",
            "been",
            "would",
            "could",
            "should",
            "there",
            "their",
            "then",
        }
        unique_terms: list[str] = []
        for term in terms:
            if term in stop_words or term in unique_terms:
                continue
            unique_terms.append(term)
        return unique_terms

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().astimezone().isoformat()

    @staticmethod
    def _today_string() -> str:
        return datetime.now().astimezone().strftime("%Y-%m-%d")

    @staticmethod
    def _now_human() -> str:
        return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


class ConsolidationThread:
    """Daemon thread that runs nightly memory consolidation for all agents.

    Wakes up once per hour, checks whether the configured hour has passed
    today, and if so runs ``MemoryStore.consolidate_agent_notes()`` for every
    agent directory found under ``agents_dir``.  Runs at most once per
    calendar day to avoid duplicate consolidations.
    """

    def __init__(
        self,
        memory_store: MemoryStore,
        model_runner: ModelRunner,
        agents_dir: Path,
        *,
        hour: int = 2,
        keep_days: int = 3,
        working_directory: Path,
    ) -> None:
        self._memory = memory_store
        self._model_runner = model_runner
        self._agents_dir = agents_dir
        self._hour = hour
        self._keep_days = keep_days
        self._working_dir = working_directory
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_run_date: str | None = None  # "YYYY-MM-DD"

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="consolidation",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info(
            "ConsolidationThread started (hour=%s, keep_days=%s)",
            self._hour,
            self._keep_days,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._maybe_consolidate()
            except Exception:
                LOGGER.exception("ConsolidationThread unexpected error")
            # Wake up once an hour; use wait() so stop() unblocks promptly
            self._stop_event.wait(3600)

    def _maybe_consolidate(self) -> None:
        now = datetime.now().astimezone()
        today = now.strftime("%Y-%m-%d")

        # Only run once per day, after the configured hour
        if self._last_run_date == today:
            return
        if now.hour < self._hour:
            return

        self._last_run_date = today
        LOGGER.info("ConsolidationThread starting nightly run for date=%s", today)

        if not self._agents_dir.exists():
            return

        for agent_dir in sorted(self._agents_dir.iterdir()):
            if not agent_dir.is_dir():
                continue
            agent = agent_dir.name
            try:
                result = self._memory.consolidate_agent_notes(
                    agent,
                    self._model_runner,
                    self._working_dir,
                    keep_days=self._keep_days,
                )
                LOGGER.info("Consolidation agent=%s result=%r", agent, result)
            except Exception:
                LOGGER.exception("Consolidation failed for agent=%s", agent)


def _parse_date_from_stem(stem: str) -> "datetime.date | None":
    """Return a date if the stem is in YYYY-MM-DD format, else None."""
    import datetime as _dt
    try:
        return _dt.date.fromisoformat(stem)
    except ValueError:
        return None
