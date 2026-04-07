from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .memory import MemoryStore
    from .model_runner import ModelRunner
    from .scheduler import Task, TaskStore

LOGGER = logging.getLogger(__name__)

# (surface, chat_id, text) -> None
SendCallback = Callable[[str, str, str], None]


class BriefingThread:
    """Daemon thread that sends scheduled briefings to configured chats.

    Wakes up once per hour and checks if the current local hour matches any of
    the configured ``times``.  At each matching hour, generates a personalised
    briefing via Claude and sends it to all registered targets.  Each
    (date, hour) slot fires at most once, so multiple restarts within the same
    hour are safe.
    """

    def __init__(
        self,
        *,
        task_store: TaskStore,
        memory_store: MemoryStore,
        model_runner: ModelRunner,
        agents_dir: Path,
        default_agent: str,
        enabled: bool = False,
        times: list[int] | None = None,
        working_directory: Path,
    ) -> None:
        self._task_store = task_store
        self._memory = memory_store
        self._model_runner = model_runner
        self._agents_dir = agents_dir
        self._default_agent = default_agent
        self._enabled = enabled
        self._times: list[int] = list(times or [9])
        self._working_dir = working_directory
        self._senders: dict[str, SendCallback] = {}
        self._targets: dict[str, list[str]] = {}  # sender_key -> [chat_id, ...]
        self._fired_keys: set[str] = set()         # "YYYY-MM-DD:HH" slots already fired
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ── Public configuration ─────────────────────────────────────────────────

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def set_times(self, times: list[int]) -> None:
        self._times = list(times)

    def get_enabled(self) -> bool:
        return self._enabled

    def get_times(self) -> list[int]:
        return list(self._times)

    # ── Registration ─────────────────────────────────────────────────────────

    def register_sender(self, key: str, callback: SendCallback) -> None:
        """Register a send callback. key = f"{platform}:{account_id}"."""
        self._senders[key] = callback

    def register_target(self, key: str, chat_id: str) -> None:
        """Register a chat_id to receive briefings for the given sender key."""
        self._targets.setdefault(key, [])
        if chat_id not in self._targets[key]:
            self._targets[key].append(chat_id)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="briefing",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info(
            "BriefingThread started (enabled=%s, times=%s)",
            self._enabled,
            self._times,
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    # ── On-demand generation (for /briefing now) ─────────────────────────────

    def generate_briefing_text(self, agent: str, chat_id: str) -> str:
        """Generate and return a briefing string. Does not send."""
        pending = self._task_store.list_pending(chat_id)
        yesterday_str = (datetime.now().astimezone() - timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday_note = self._read_daily_note(agent, yesterday_str)
        today_str = datetime.now().astimezone().strftime("%A, %-d %B %Y")
        prompt = _build_briefing_prompt(today_str, pending, yesterday_note)
        try:
            result = self._model_runner.run_prompt(prompt, self._working_dir, effort="low")
            return result.stdout.strip() or "Good morning! Nothing urgent today."
        except Exception as exc:
            LOGGER.warning("Briefing generation failed: %s", exc)
            return "Good morning! (Briefing generation failed.)"

    # ── Internal ─────────────────────────────────────────────────────────────

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._maybe_send_briefings()
            except Exception:
                LOGGER.exception("BriefingThread unexpected error")
            self._stop_event.wait(3600)

    def _maybe_send_briefings(self) -> None:
        if not self._enabled:
            return
        if not self._times:
            return

        now = datetime.now().astimezone()
        today = now.strftime("%Y-%m-%d")
        hour = now.hour

        run_key = f"{today}:{hour:02d}"
        if run_key in self._fired_keys:
            return
        if hour not in self._times:
            return

        self._fired_keys.add(run_key)
        # Prune stale keys (keep only today's entries)
        self._fired_keys = {k for k in self._fired_keys if k >= today}

        for sender_key, chat_ids in self._targets.items():
            for chat_id in chat_ids:
                try:
                    self._send_briefing(sender_key, chat_id)
                except Exception:
                    LOGGER.exception(
                        "Briefing send failed for key=%s chat=%s", sender_key, chat_id
                    )

    def _send_briefing(self, sender_key: str, chat_id: str) -> None:
        sender = self._senders.get(sender_key)
        if sender is None:
            LOGGER.warning("No sender registered for briefing key=%s", sender_key)
            return
        surface = sender_key.split(":")[0]
        text = self.generate_briefing_text(self._default_agent, chat_id)
        sender(surface, chat_id, text)
        LOGGER.info("Briefing sent to chat_id=%s via key=%s", chat_id, sender_key)

    def _read_daily_note(self, agent: str, date_str: str) -> str:
        note_path = self._agents_dir / agent / "memory" / f"{date_str}.md"
        if not note_path.exists():
            return ""
        return note_path.read_text(encoding="utf-8").strip()


def _build_briefing_prompt(
    today_str: str,
    pending_tasks: list[Task],
    yesterday_note: str,
) -> str:
    if pending_tasks:
        task_lines: list[str] = []
        for task in pending_tasks:
            msg = task.payload.get("message", "")
            fire_time = task.fire_at.astimezone().strftime("%H:%M")
            task_lines.append(f"- {fire_time}: {msg}")
        reminders_text = "\n".join(task_lines)
    else:
        reminders_text = "None"

    note_section = yesterday_note.strip() if yesterday_note else "None"

    return (
        f"Today is {today_str}. You are a personal assistant sending a morning briefing.\n\n"
        f"Pending reminders:\n{reminders_text}\n\n"
        f"Yesterday's notes:\n{note_section}\n\n"
        "Generate a concise morning briefing (3–5 sentences). Start with a warm greeting that "
        "includes the day and date. Mention any pending reminders by their scheduled time if "
        "present. If there are relevant notes from yesterday, briefly acknowledge them. "
        "End with one encouraging sentence. Reply with plain text only, no markdown."
    )
