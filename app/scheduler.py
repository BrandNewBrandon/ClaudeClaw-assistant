from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


LOGGER = logging.getLogger(__name__)


class SchedulerError(Exception):
    pass


@dataclass
class Task:
    id: str
    task_type: str
    chat_id: str
    account_id: str
    surface: str
    fire_at: datetime
    payload: dict[str, Any]
    status: str
    created_at: datetime


def parse_fire_at(spec: str) -> datetime:
    """Parse a time spec into an absolute UTC datetime.

    Supported formats:
    - Relative durations: ``30s``, ``5m``, ``2h``, ``1d``
    - ISO 8601 datetime string (naive treated as UTC)
    """
    spec = spec.strip()
    now = datetime.now(tz=timezone.utc)

    if len(spec) >= 2 and spec[-1] in "smhd" and spec[:-1].lstrip("-").isdigit():
        value = int(spec[:-1])
        unit = spec[-1]
        delta_map = {
            "s": timedelta(seconds=value),
            "m": timedelta(minutes=value),
            "h": timedelta(hours=value),
            "d": timedelta(days=value),
        }
        return now + delta_map[unit]

    try:
        parsed = datetime.fromisoformat(spec)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        pass

    raise SchedulerError(
        f"Cannot parse time spec: {spec!r}. "
        "Use formats like '5m', '2h', '1d', or ISO datetime."
    )


class TaskStore:
    """SQLite-backed persistent task store."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self._connect() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id TEXT PRIMARY KEY,
                        task_type TEXT NOT NULL,
                        chat_id TEXT NOT NULL,
                        account_id TEXT NOT NULL,
                        surface TEXT NOT NULL,
                        fire_at TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TEXT NOT NULL
                    )
                """)
                conn.commit()

    def add_task(
        self,
        *,
        task_type: str,
        chat_id: str,
        account_id: str,
        surface: str,
        fire_at: datetime,
        payload: dict[str, Any],
    ) -> str:
        task_id = str(uuid.uuid4())[:8]
        created_at = datetime.now(tz=timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO tasks (id, task_type, chat_id, account_id, surface, fire_at, payload, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                    (
                        task_id,
                        task_type,
                        chat_id,
                        account_id,
                        surface,
                        fire_at.isoformat(),
                        json.dumps(payload),
                        created_at,
                    ),
                )
                conn.commit()
        return task_id

    def get_due_tasks(self) -> list[Task]:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status = 'pending' AND fire_at <= ? ORDER BY fire_at",
                    (now,),
                ).fetchall()
        return [self._row_to_task(row) for row in rows]

    def mark_fired(self, task_id: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("UPDATE tasks SET status = 'fired' WHERE id = ?", (task_id,))
                conn.commit()

    def mark_failed(self, task_id: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("UPDATE tasks SET status = 'failed' WHERE id = ?", (task_id,))
                conn.commit()

    def update_fire_at(self, task_id: str, new_fire_at: datetime) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE tasks SET fire_at = ? WHERE id = ?",
                    (new_fire_at.isoformat(), task_id),
                )
                conn.commit()

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    "UPDATE tasks SET status = 'cancelled' WHERE id = ? AND status = 'pending'",
                    (task_id,),
                )
                conn.commit()
                return cursor.rowcount > 0

    def list_pending(self, chat_id: str | None = None) -> list[Task]:
        with self._lock:
            with self._connect() as conn:
                if chat_id is not None:
                    rows = conn.execute(
                        "SELECT * FROM tasks WHERE status = 'pending' AND chat_id = ? ORDER BY fire_at",
                        (chat_id,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM tasks WHERE status = 'pending' ORDER BY fire_at"
                    ).fetchall()
        return [self._row_to_task(row) for row in rows]

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        fire_at = datetime.fromisoformat(str(row["fire_at"]))
        if fire_at.tzinfo is None:
            fire_at = fire_at.replace(tzinfo=timezone.utc)
        created_at = datetime.fromisoformat(str(row["created_at"]))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return Task(
            id=str(row["id"]),
            task_type=str(row["task_type"]),
            chat_id=str(row["chat_id"]),
            account_id=str(row["account_id"]),
            surface=str(row["surface"]),
            fire_at=fire_at,
            payload=json.loads(str(row["payload"])),
            status=str(row["status"]),
            created_at=created_at,
        )


# Callback signature: (surface, chat_id, text) -> None
SendCallback = Callable[[str, str, str], None]


class Scheduler:
    """Background thread that fires tasks at their scheduled time."""

    def __init__(
        self,
        task_store: TaskStore,
        poll_interval_seconds: int = 30,
        *,
        quiet_hours_start: str | None = None,
        quiet_hours_end: str | None = None,
    ) -> None:
        self._store = task_store
        self._poll_interval = poll_interval_seconds
        self._send_callbacks: dict[str, SendCallback] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        # Quiet hours: "HH:MM" strings (24-hour). Both None = disabled.
        self._quiet_start = quiet_hours_start
        self._quiet_end = quiet_hours_end

    def get_quiet_hours(self) -> tuple[str | None, str | None]:
        """Return (start, end) quiet hours strings, or (None, None) if disabled."""
        return self._quiet_start, self._quiet_end

    def set_quiet_hours(self, start: str | None, end: str | None) -> None:
        """Update quiet hours at runtime. Pass both as None to disable."""
        self._quiet_start = start
        self._quiet_end = end

    def register_sender(self, surface: str, callback: SendCallback) -> None:
        self._send_callbacks[surface] = callback

    def send_to(self, surface: str, chat_id: str, text: str) -> None:
        """Send a message to a specific surface/chat via registered callback."""
        callback = self._send_callbacks.get(surface)
        if callback is None:
            raise SchedulerError(f"No sender registered for surface: {surface!r}")
        callback(surface, chat_id, text)

    def add_reminder(
        self,
        *,
        chat_id: str,
        account_id: str,
        surface: str,
        fire_at: datetime,
        message: str,
    ) -> str:
        return self._store.add_task(
            task_type="remind",
            chat_id=chat_id,
            account_id=account_id,
            surface=surface,
            fire_at=fire_at,
            payload={"message": message},
        )

    def list_tasks(self, chat_id: str) -> list[Task]:
        return self._store.list_pending(chat_id=chat_id)

    def cancel_task(self, task_id: str) -> bool:
        return self._store.cancel_task(task_id)

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="scheduler",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info("Scheduler started (poll_interval=%ss)", self._poll_interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception:
                LOGGER.exception("Scheduler tick error")
            self._stop_event.wait(self._poll_interval)

    def _tick(self) -> None:
        due = self._store.get_due_tasks()
        for task in due:
            try:
                deferred_to = self._quiet_defer()
                if deferred_to is not None:
                    self._store.update_fire_at(task.id, deferred_to)
                    LOGGER.info(
                        "Scheduler deferred task id=%s to %s (quiet hours)",
                        task.id,
                        deferred_to.isoformat(),
                    )
                    continue
                self._fire_task(task)
                self._store.mark_fired(task.id)
                LOGGER.info(
                    "Scheduler fired task id=%s type=%s chat_id=%s",
                    task.id,
                    task.task_type,
                    task.chat_id,
                )
            except Exception as exc:
                self._store.mark_failed(task.id)
                LOGGER.exception("Scheduler failed to fire task id=%s: %s", task.id, exc)

    def _quiet_defer(self) -> datetime | None:
        """Return the datetime quiet hours end if we're currently in the quiet window, else None."""
        if not self._quiet_start or not self._quiet_end:
            return None

        try:
            now = datetime.now().astimezone()
            now_minutes = now.hour * 60 + now.minute

            start_h, start_m = (int(x) for x in self._quiet_start.split(":"))
            end_h, end_m = (int(x) for x in self._quiet_end.split(":"))
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m

            if start_minutes < end_minutes:
                # Same-day window, e.g. 01:00–08:00
                in_quiet = start_minutes <= now_minutes < end_minutes
            else:
                # Overnight window, e.g. 22:00–08:00
                in_quiet = now_minutes >= start_minutes or now_minutes < end_minutes

            if not in_quiet:
                return None

            # Return today's end time, or tomorrow's if end is before now (overnight)
            end_today = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
            if end_today <= now:
                end_today = end_today + timedelta(days=1)
            return end_today

        except (ValueError, AttributeError):
            LOGGER.warning("Invalid quiet_hours config: start=%r end=%r", self._quiet_start, self._quiet_end)
            return None

    def _fire_task(self, task: Task) -> None:
        callback = self._send_callbacks.get(task.surface)
        if callback is None:
            raise SchedulerError(f"No sender registered for surface: {task.surface!r}")

        if task.task_type == "remind":
            message = task.payload.get("message", "(reminder)")
            callback(task.surface, task.chat_id, f"Reminder: {message}")
        elif task.task_type == "send_message":
            text = task.payload.get("text", "")
            callback(task.surface, task.chat_id, text)
        else:
            raise SchedulerError(f"Unknown task type: {task.task_type!r}")
