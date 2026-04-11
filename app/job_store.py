"""SQLite-backed store for background jobs."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Job:
    id: str
    chat_id: str
    account_id: str
    surface: str
    agent: str
    prompt: str
    status: str  # pending, running, completed, failed, cancelled
    result: str | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class JobStore:
    """SQLite-backed persistent job store."""

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
                    CREATE TABLE IF NOT EXISTS jobs (
                        id TEXT PRIMARY KEY,
                        chat_id TEXT NOT NULL,
                        account_id TEXT NOT NULL,
                        surface TEXT NOT NULL,
                        agent TEXT NOT NULL,
                        prompt TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        result TEXT,
                        error TEXT,
                        created_at TEXT NOT NULL,
                        started_at TEXT,
                        completed_at TEXT
                    )
                """)
                conn.commit()

    def create_job(self, *, chat_id: str, account_id: str, surface: str, agent: str, prompt: str) -> str:
        job_id = str(uuid.uuid4())[:8]
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO jobs (id, chat_id, account_id, surface, agent, prompt, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
                    (job_id, chat_id, account_id, surface, agent, prompt, now),
                )
                conn.commit()
        return job_id

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_job(row)

    def claim_next_pending(self) -> Job | None:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM jobs WHERE status = 'pending' ORDER BY created_at LIMIT 1"
                ).fetchone()
                if row is None:
                    return None
                conn.execute(
                    "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ?",
                    (now, row["id"]),
                )
                conn.commit()
                row = conn.execute("SELECT * FROM jobs WHERE id = ?", (row["id"],)).fetchone()
        return self._row_to_job(row)

    def complete_job(self, job_id: str, *, result: str) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE jobs SET status = 'completed', result = ?, completed_at = ? WHERE id = ?",
                    (result, now, job_id),
                )
                conn.commit()

    def fail_job(self, job_id: str, *, error: str) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE jobs SET status = 'failed', error = ?, completed_at = ? WHERE id = ?",
                    (error, now, job_id),
                )
                conn.commit()

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    "UPDATE jobs SET status = 'cancelled' WHERE id = ? AND status IN ('pending', 'running')",
                    (job_id,),
                )
                conn.commit()
                return cursor.rowcount > 0

    def list_jobs(self, chat_id: str | None = None, *, limit: int = 20) -> list[Job]:
        with self._lock:
            with self._connect() as conn:
                if chat_id is not None:
                    rows = conn.execute(
                        "SELECT * FROM jobs WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
                        (chat_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,),
                    ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def running_count(self) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) as cnt FROM jobs WHERE status = 'running'").fetchone()
        return int(row["cnt"])

    def recover_stale_jobs(self) -> int:
        """Mark any 'running' jobs as failed (orphaned from a prior crash). Returns count."""
        now = datetime.now(tz=timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    "UPDATE jobs SET status = 'failed', error = 'Runtime restarted while job was running', completed_at = ? "
                    "WHERE status = 'running'",
                    (now,),
                )
                conn.commit()
                return cursor.rowcount

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        return Job(
            id=str(row["id"]),
            chat_id=str(row["chat_id"]),
            account_id=str(row["account_id"]),
            surface=str(row["surface"]),
            agent=str(row["agent"]),
            prompt=str(row["prompt"]),
            status=str(row["status"]),
            result=row["result"],
            error=row["error"],
            created_at=JobStore._parse_dt(str(row["created_at"])) or datetime.now(tz=timezone.utc),
            started_at=JobStore._parse_dt(row["started_at"]),
            completed_at=JobStore._parse_dt(row["completed_at"]),
        )
