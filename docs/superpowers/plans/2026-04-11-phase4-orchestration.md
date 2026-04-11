# Phase 4 — Orchestration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add background jobs, proactive system monitors, and agent delegation to the assistant runtime.

**Architecture:** Three independent subsystems: JobStore/JobRunner for background work, MonitorRunner for system health alerts, and delegation via background jobs with alternate agent context. All follow existing patterns (SQLite persistence, daemon threads, send callbacks).

**Tech Stack:** Python 3.11+, SQLite, threading, pytest

---

### Task 1: JobStore — SQLite persistence for background jobs

**Files:**
- Create: `app/job_store.py`
- Create: `tests/test_job_store.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_job_store.py`:

```python
from __future__ import annotations

from pathlib import Path

from app.job_store import JobStore, Job


def test_create_job_returns_id(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(
        chat_id="c1", account_id="primary", surface="telegram:primary",
        agent="main", prompt="do something",
    )
    assert isinstance(job_id, str)
    assert len(job_id) == 8


def test_get_job_returns_created_job(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(
        chat_id="c1", account_id="primary", surface="telegram:primary",
        agent="main", prompt="do something",
    )
    job = store.get_job(job_id)
    assert job is not None
    assert job.id == job_id
    assert job.prompt == "do something"
    assert job.status == "pending"
    assert job.agent == "main"


def test_get_job_returns_none_for_missing(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    assert store.get_job("nonexist") is None


def test_claim_pending_job(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(
        chat_id="c1", account_id="primary", surface="telegram:primary",
        agent="main", prompt="task",
    )
    job = store.claim_next_pending()
    assert job is not None
    assert job.id == job_id
    assert job.status == "running"
    # Second claim returns None (already running)
    assert store.claim_next_pending() is None


def test_complete_job(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(
        chat_id="c1", account_id="primary", surface="telegram:primary",
        agent="main", prompt="task",
    )
    store.claim_next_pending()
    store.complete_job(job_id, result="done!")
    job = store.get_job(job_id)
    assert job is not None
    assert job.status == "completed"
    assert job.result == "done!"


def test_fail_job(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(
        chat_id="c1", account_id="primary", surface="telegram:primary",
        agent="main", prompt="task",
    )
    store.claim_next_pending()
    store.fail_job(job_id, error="timeout")
    job = store.get_job(job_id)
    assert job is not None
    assert job.status == "failed"
    assert job.error == "timeout"


def test_cancel_job(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(
        chat_id="c1", account_id="primary", surface="telegram:primary",
        agent="main", prompt="task",
    )
    assert store.cancel_job(job_id) is True
    job = store.get_job(job_id)
    assert job is not None
    assert job.status == "cancelled"


def test_list_jobs(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    store.create_job(chat_id="c1", account_id="primary", surface="s", agent="main", prompt="a")
    store.create_job(chat_id="c1", account_id="primary", surface="s", agent="main", prompt="b")
    store.create_job(chat_id="c2", account_id="primary", surface="s", agent="main", prompt="c")
    jobs = store.list_jobs("c1")
    assert len(jobs) == 2
    all_jobs = store.list_jobs()
    assert len(all_jobs) == 3


def test_running_count(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    store.create_job(chat_id="c1", account_id="primary", surface="s", agent="main", prompt="a")
    store.create_job(chat_id="c1", account_id="primary", surface="s", agent="main", prompt="b")
    assert store.running_count() == 0
    store.claim_next_pending()
    assert store.running_count() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_job_store.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement job_store.py**

Create `app/job_store.py`:

```python
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
        conn = sqlite3.connect(str(self._db_path))
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

    def create_job(
        self,
        *,
        chat_id: str,
        account_id: str,
        surface: str,
        agent: str,
        prompt: str,
    ) -> str:
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
        """Atomically claim the oldest pending job by setting status to 'running'."""
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
                # Re-fetch to get updated status
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
                        "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def running_count(self) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) as cnt FROM jobs WHERE status = 'running'").fetchone()
        return int(row["cnt"])

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
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_job_store.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/job_store.py tests/test_job_store.py
git commit -m "feat: add JobStore for background job persistence"
```

---

### Task 2: JobRunner — background execution engine

**Files:**
- Create: `app/job_runner.py`
- Create: `tests/test_job_runner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_job_runner.py`:

```python
from __future__ import annotations

import time
from pathlib import Path
from dataclasses import dataclass

from app.job_store import JobStore
from app.job_runner import JobRunner


@dataclass
class FakeModelResult:
    stdout: str
    stderr: str = ""
    exit_code: int = 0
    session_id: str | None = None


class FakeRunner:
    def __init__(self, response: str = "done"):
        self._response = response

    def run_prompt(self, prompt, working_directory, **kwargs):
        return FakeModelResult(stdout=self._response)


class FakeContextBuilder:
    def __init__(self, agents_dir: Path):
        pass

    def load_agent_context(self, agent_name: str):
        return None

    def build_prompt(self, agent_context, user_message, **kwargs):
        return user_message


def test_job_runner_processes_pending_job(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)

    sent: list[tuple[str, str, str]] = []
    def fake_send(surface, chat_id, text):
        sent.append((surface, chat_id, text))

    runner = JobRunner(
        job_store=store,
        model_runner=FakeRunner("result text"),
        agents_dir=agents_dir,
        max_concurrent=2,
    )
    runner.register_sender("telegram:primary", fake_send)

    job_id = store.create_job(
        chat_id="c1", account_id="primary", surface="telegram:primary",
        agent="main", prompt="do something",
    )
    runner.tick()
    # Give thread time to complete
    time.sleep(0.5)

    job = store.get_job(job_id)
    assert job is not None
    assert job.status == "completed"
    assert job.result == "result text"
    assert len(sent) == 1
    assert "result text" in sent[0][2]


def test_job_runner_respects_max_concurrent(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)

    runner = JobRunner(
        job_store=store,
        model_runner=FakeRunner("ok"),
        agents_dir=agents_dir,
        max_concurrent=1,
    )
    runner.register_sender("s", lambda s, c, t: None)

    store.create_job(chat_id="c1", account_id="primary", surface="s", agent="main", prompt="a")
    store.create_job(chat_id="c1", account_id="primary", surface="s", agent="main", prompt="b")

    runner.tick()
    # Only one should be running
    assert store.running_count() <= 1


def test_job_runner_handles_model_error(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)

    class ErrorRunner:
        def run_prompt(self, prompt, working_directory, **kwargs):
            raise RuntimeError("model exploded")

    sent: list[tuple[str, str, str]] = []
    runner = JobRunner(
        job_store=store,
        model_runner=ErrorRunner(),
        agents_dir=agents_dir,
        max_concurrent=2,
    )
    runner.register_sender("s", lambda s, c, t: sent.append((s, c, t)))

    job_id = store.create_job(
        chat_id="c1", account_id="primary", surface="s",
        agent="main", prompt="fail",
    )
    runner.tick()
    time.sleep(0.5)

    job = store.get_job(job_id)
    assert job is not None
    assert job.status == "failed"
    assert "model exploded" in (job.error or "")
    assert len(sent) == 1
    assert "error" in sent[0][2].lower() or "failed" in sent[0][2].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_job_runner.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement job_runner.py**

Create `app/job_runner.py`:

```python
"""Background job execution engine."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable

from .context_builder import ContextBuilder
from .job_store import JobStore

LOGGER = logging.getLogger(__name__)

SendCallback = Callable[[str, str, str], None]


class JobRunner:
    """Picks up pending jobs and runs them in background threads."""

    def __init__(
        self,
        *,
        job_store: JobStore,
        model_runner: Any,  # ModelRunner or compatible
        agents_dir: Path,
        max_concurrent: int = 2,
        poll_interval: int = 10,
    ) -> None:
        self._store = job_store
        self._model_runner = model_runner
        self._agents_dir = agents_dir
        self._max_concurrent = max_concurrent
        self._poll_interval = poll_interval
        self._send_callbacks: dict[str, SendCallback] = {}
        self._context_builder = ContextBuilder(agents_dir=agents_dir)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def register_sender(self, surface: str, callback: SendCallback) -> None:
        self._send_callbacks[surface] = callback

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="job-runner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception:
                LOGGER.exception("JobRunner tick error")
            self._stop_event.wait(self._poll_interval)

    def tick(self) -> None:
        """Process pending jobs up to max_concurrent limit."""
        while self._store.running_count() < self._max_concurrent:
            job = self._store.claim_next_pending()
            if job is None:
                break
            thread = threading.Thread(
                target=self._execute_job,
                args=(job.id, job.prompt, job.agent, job.surface, job.chat_id),
                name=f"job-{job.id}",
                daemon=True,
            )
            thread.start()

    def _execute_job(
        self, job_id: str, prompt: str, agent: str, surface: str, chat_id: str,
    ) -> None:
        try:
            working_dir = self._agents_dir / agent
            agent_context = self._context_builder.load_agent_context(agent)
            full_prompt = self._context_builder.build_prompt(
                agent_context, prompt,
                recent_transcript=[],
                relevant_memory=[],
                tool_instructions="",
            )
            result = self._model_runner.run_prompt(
                prompt=full_prompt,
                working_directory=working_dir,
            )
            output = result.stdout.strip() or "(no response)"
            self._store.complete_job(job_id, result=output)
            self._deliver(surface, chat_id, f"Background job [{job_id}] completed:\n\n{output}")
        except Exception as exc:
            error_msg = str(exc)
            self._store.fail_job(job_id, error=error_msg)
            self._deliver(surface, chat_id, f"Background job [{job_id}] failed: {error_msg}")
            LOGGER.exception("Job %s failed", job_id)

    def _deliver(self, surface: str, chat_id: str, text: str) -> None:
        callback = self._send_callbacks.get(surface)
        if callback is None:
            LOGGER.warning("No sender for surface=%s, cannot deliver job result", surface)
            return
        try:
            callback(surface, chat_id, text)
        except Exception:
            LOGGER.exception("Failed to deliver job result to surface=%s chat_id=%s", surface, chat_id)
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_job_runner.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/job_runner.py tests/test_job_runner.py
git commit -m "feat: add JobRunner for background job execution"
```

---

### Task 3: MonitorRunner — proactive system health alerts

**Files:**
- Create: `app/monitors.py`
- Create: `tests/test_monitors.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_monitors.py`:

```python
from __future__ import annotations

from app.monitors import MonitorRunner, disk_usage_monitor, process_count_monitor


def test_monitor_runner_fires_alert():
    sent: list[tuple[str, str, str]] = []
    runner = MonitorRunner(cooldown_seconds=0)
    runner.register_sender("s", lambda s, c, t: sent.append((s, c, t)))
    runner.register_target("s", "c1")
    runner.register_monitor("test", lambda: "Alert!")
    runner.tick()
    assert len(sent) == 1
    assert "Alert!" in sent[0][2]


def test_monitor_runner_no_alert_when_none():
    sent: list[tuple[str, str, str]] = []
    runner = MonitorRunner(cooldown_seconds=0)
    runner.register_sender("s", lambda s, c, t: sent.append((s, c, t)))
    runner.register_target("s", "c1")
    runner.register_monitor("test", lambda: None)
    runner.tick()
    assert len(sent) == 0


def test_monitor_runner_cooldown_prevents_repeat():
    sent: list[tuple[str, str, str]] = []
    runner = MonitorRunner(cooldown_seconds=3600)
    runner.register_sender("s", lambda s, c, t: sent.append((s, c, t)))
    runner.register_target("s", "c1")
    runner.register_monitor("test", lambda: "Alert!")
    runner.tick()
    runner.tick()  # Should be suppressed by cooldown
    assert len(sent) == 1


def test_disk_usage_monitor_returns_none_normally():
    # Normal disk usage should not trigger alert
    result = disk_usage_monitor(threshold_percent=99.9)()
    assert result is None


def test_process_count_monitor_returns_none_normally():
    # Normal process count should not trigger alert
    result = process_count_monitor(threshold=99999)()
    assert result is None


def test_monitor_runner_enabled_toggle():
    runner = MonitorRunner()
    assert runner.enabled is True
    runner.enabled = False
    assert runner.enabled is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_monitors.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement monitors.py**

Create `app/monitors.py`:

```python
"""Proactive system health monitors."""
from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from typing import Callable

LOGGER = logging.getLogger(__name__)

MonitorFn = Callable[[], str | None]
SendCallback = Callable[[str, str, str], None]


class MonitorRunner:
    """Runs registered monitors periodically and alerts on triggers."""

    def __init__(
        self,
        *,
        poll_interval: int = 300,
        cooldown_seconds: int = 3600,
    ) -> None:
        self._poll_interval = poll_interval
        self._cooldown_seconds = cooldown_seconds
        self._monitors: dict[str, MonitorFn] = {}
        self._send_callbacks: dict[str, SendCallback] = {}
        self._targets: dict[str, list[str]] = {}
        self._last_fired: dict[str, float] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def register_monitor(self, name: str, fn: MonitorFn) -> None:
        self._monitors[name] = fn

    def register_sender(self, surface: str, callback: SendCallback) -> None:
        self._send_callbacks[surface] = callback

    def register_target(self, surface: str, chat_id: str) -> None:
        self._targets.setdefault(surface, [])
        if chat_id not in self._targets[surface]:
            self._targets[surface].append(chat_id)

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="monitor-runner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception:
                LOGGER.exception("MonitorRunner tick error")
            self._stop_event.wait(self._poll_interval)

    def tick(self) -> None:
        if not self._enabled:
            return
        now = time.monotonic()
        for name, fn in self._monitors.items():
            # Cooldown check
            last = self._last_fired.get(name, 0.0)
            if now - last < self._cooldown_seconds:
                continue
            try:
                alert = fn()
            except Exception:
                LOGGER.exception("Monitor %s raised", name)
                continue
            if alert is None:
                continue
            self._last_fired[name] = now
            self._broadcast(f"[Monitor: {name}] {alert}")

    def _broadcast(self, text: str) -> None:
        for surface, chat_ids in self._targets.items():
            callback = self._send_callbacks.get(surface)
            if callback is None:
                continue
            for chat_id in chat_ids:
                try:
                    callback(surface, chat_id, text)
                except Exception:
                    LOGGER.exception("Failed to send monitor alert to %s:%s", surface, chat_id)

    def monitor_names(self) -> list[str]:
        return list(self._monitors.keys())


def disk_usage_monitor(*, threshold_percent: float = 90.0, path: str = "/") -> MonitorFn:
    """Factory: returns a monitor that alerts if disk usage exceeds threshold."""
    def check() -> str | None:
        usage = shutil.disk_usage(path)
        percent = (usage.used / usage.total) * 100
        if percent >= threshold_percent:
            free_gb = usage.free / (1024 ** 3)
            return f"Disk usage at {percent:.1f}% — {free_gb:.1f} GB free on {path}"
        return None
    return check


def process_count_monitor(*, threshold: int = 500) -> MonitorFn:
    """Factory: returns a monitor that alerts if process count is high."""
    def check() -> str | None:
        try:
            result = subprocess.run(
                ["ps", "aux"], capture_output=True, text=True, timeout=5,
            )
            count = len(result.stdout.strip().splitlines()) - 1  # subtract header
            if count >= threshold:
                return f"High process count: {count} processes running (threshold: {threshold})"
        except Exception:
            pass
        return None
    return check
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_monitors.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/monitors.py tests/test_monitors.py
git commit -m "feat: add MonitorRunner for proactive system health alerts"
```

---

### Task 4: Commands — /bg, /jobs, /job, /delegate, /monitors

**Files:**
- Modify: `app/commands.py`
- Create: `tests/test_job_commands.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_job_commands.py`:

```python
from __future__ import annotations

from pathlib import Path
from app.commands import CommandHandler
from app.job_store import JobStore
from app.job_runner import JobRunner
from app.monitors import MonitorRunner
from app.runtime_state import RuntimeState


def _make_handler(tmp_path, job_store=None, job_runner=None, monitor_runner=None):
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)
    (agents_dir / "builder").mkdir(parents=True)
    return CommandHandler(
        agents_dir=agents_dir,
        job_store=job_store,
        job_runner=job_runner,
        monitor_runner=monitor_runner,
    )


def test_bg_creates_job(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    handler = _make_handler(tmp_path, job_store=store)
    reply, _, _, _ = handler.handle(
        "/bg research quantum computing",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
        surface="telegram:primary", chat_id="c1", account_id="primary",
    )
    assert "queued" in reply.lower() or "started" in reply.lower()
    jobs = store.list_jobs("c1")
    assert len(jobs) == 1
    assert jobs[0].prompt == "research quantum computing"


def test_bg_no_store(tmp_path):
    handler = _make_handler(tmp_path)
    reply, _, _, _ = handler.handle(
        "/bg do stuff",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
    )
    assert "not available" in reply.lower()


def test_jobs_lists_jobs(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    store.create_job(chat_id="c1", account_id="primary", surface="s", agent="main", prompt="task one")
    handler = _make_handler(tmp_path, job_store=store)
    reply, _, _, _ = handler.handle(
        "/jobs",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
        chat_id="c1",
    )
    assert "task one" in reply


def test_jobs_empty(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    handler = _make_handler(tmp_path, job_store=store)
    reply, _, _, _ = handler.handle(
        "/jobs",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
        chat_id="c1",
    )
    assert "No jobs" in reply or "no jobs" in reply.lower()


def test_job_status(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(chat_id="c1", account_id="primary", surface="s", agent="main", prompt="my task")
    handler = _make_handler(tmp_path, job_store=store)
    reply, _, _, _ = handler.handle(
        f"/job {job_id}",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
    )
    assert job_id in reply
    assert "pending" in reply.lower()


def test_job_cancel(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(chat_id="c1", account_id="primary", surface="s", agent="main", prompt="cancel me")
    handler = _make_handler(tmp_path, job_store=store)
    reply, _, _, _ = handler.handle(
        f"/job cancel {job_id}",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
    )
    assert "cancelled" in reply.lower()


def test_delegate_creates_job_for_other_agent(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    handler = _make_handler(tmp_path, job_store=store)
    reply, _, _, _ = handler.handle(
        "/delegate builder write a hello world script",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
        surface="telegram:primary", chat_id="c1", account_id="primary",
    )
    assert "delegated" in reply.lower() or "queued" in reply.lower()
    jobs = store.list_jobs("c1")
    assert len(jobs) == 1
    assert jobs[0].agent == "builder"


def test_delegate_unknown_agent(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    handler = _make_handler(tmp_path, job_store=store)
    reply, _, _, _ = handler.handle(
        "/delegate nonexistent do stuff",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
    )
    assert "unknown" in reply.lower() or "not found" in reply.lower()


def test_monitors_status(tmp_path):
    monitor = MonitorRunner()
    monitor.register_monitor("disk", lambda: None)
    handler = _make_handler(tmp_path, monitor_runner=monitor)
    reply, _, _, _ = handler.handle(
        "/monitors",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
    )
    assert "disk" in reply.lower()
    assert "enabled" in reply.lower()


def test_monitors_toggle(tmp_path):
    monitor = MonitorRunner()
    handler = _make_handler(tmp_path, monitor_runner=monitor)
    reply, _, _, _ = handler.handle(
        "/monitors off",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
    )
    assert monitor.enabled is False
    assert "disabled" in reply.lower()
```

- [ ] **Step 2: Implement commands**

In `app/commands.py`:

1. Add `job_store`, `job_runner`, and `monitor_runner` parameters to `__init__`:

```python
def __init__(
    self,
    agents_dir: Path,
    ...existing params...,
    job_store: "JobStore | None" = None,
    job_runner: "JobRunner | None" = None,
    monitor_runner: "MonitorRunner | None" = None,
) -> None:
    ...existing assignments...
    self._job_store = job_store
    self._job_runner = job_runner
    self._monitor_runner = monitor_runner
```

Add to TYPE_CHECKING block:
```python
from .job_store import JobStore
from .job_runner import JobRunner
from .monitors import MonitorRunner
```

2. Add commands before `/help`:

```python
        # ── /bg <prompt> ─────────────────────────────────────────────────────
        if stripped.startswith("/bg "):
            prompt = stripped.removeprefix("/bg ").strip()
            if not prompt:
                return ("Usage: /bg <prompt>", None, False, None)
            if self._job_store is None:
                return ("Background jobs not available.", None, False, None)
            job_id = self._job_store.create_job(
                chat_id=chat_id or "",
                account_id=account_id or "primary",
                surface=surface,
                agent=active_agent,
                prompt=prompt,
            )
            return (f"Background job queued [{job_id}]. You'll be notified when it completes.", None, False, None)

        # ── /jobs ────────────────────────────────────────────────────────────
        if stripped == "/jobs":
            if self._job_store is None:
                return ("Background jobs not available.", None, False, None)
            jobs = self._job_store.list_jobs(chat_id)
            if not jobs:
                return ("No jobs found.", None, False, None)
            lines = [f"Jobs ({len(jobs)}):"]
            for job in jobs:
                status_icon = {"pending": "⏳", "running": "▶️", "completed": "✅", "failed": "❌", "cancelled": "🚫"}.get(job.status, "?")
                preview = job.prompt[:60] + ("…" if len(job.prompt) > 60 else "")
                lines.append(f"  {status_icon} [{job.id}] {job.status} — {preview}")
            return ("\n".join(lines), None, False, None)

        # ── /job <id> or /job cancel <id> ────────────────────────────────────
        if stripped.startswith("/job "):
            rest = stripped.removeprefix("/job ").strip()
            if self._job_store is None:
                return ("Background jobs not available.", None, False, None)
            if rest.startswith("cancel "):
                job_id = rest.removeprefix("cancel ").strip()
                if self._job_store.cancel_job(job_id):
                    return (f"Job {job_id} cancelled.", None, False, None)
                return (f"Could not cancel job {job_id} (not found or already completed).", None, False, None)
            job = self._job_store.get_job(rest)
            if job is None:
                return (f"No job found with ID {rest}.", None, False, None)
            lines = [
                f"Job [{job.id}]",
                f"Status: {job.status}",
                f"Agent: {job.agent}",
                f"Prompt: {job.prompt[:200]}",
                f"Created: {job.created_at.isoformat()[:16]}",
            ]
            if job.started_at:
                lines.append(f"Started: {job.started_at.isoformat()[:16]}")
            if job.completed_at:
                lines.append(f"Completed: {job.completed_at.isoformat()[:16]}")
            if job.result:
                lines.append(f"Result: {job.result[:500]}")
            if job.error:
                lines.append(f"Error: {job.error}")
            return ("\n".join(lines), None, False, None)

        # ── /delegate <agent> <prompt> ───────────────────────────────────────
        if stripped.startswith("/delegate "):
            rest = stripped.removeprefix("/delegate ").strip()
            parts = rest.split(maxsplit=1)
            if len(parts) < 2:
                return ("Usage: /delegate <agent> <prompt>", None, False, None)
            target_agent, prompt = parts[0], parts[1]
            if not (self._agents_dir / target_agent).exists():
                return (f"Unknown agent: {target_agent}", None, False, None)
            if self._job_store is None:
                return ("Background jobs not available.", None, False, None)
            job_id = self._job_store.create_job(
                chat_id=chat_id or "",
                account_id=account_id or "primary",
                surface=surface,
                agent=target_agent,
                prompt=prompt,
            )
            return (f"Delegated to {target_agent} [{job_id}]. You'll be notified when it completes.", None, False, None)

        # ── /monitors ────────────────────────────────────────────────────────
        if stripped == "/monitors" or stripped.startswith("/monitors "):
            if self._monitor_runner is None:
                return ("Monitors not available.", None, False, None)
            parts = stripped.split(maxsplit=1)
            sub = parts[1].strip().lower() if len(parts) > 1 else None
            if sub == "on":
                self._monitor_runner.enabled = True
                return ("Monitors enabled.", None, False, None)
            if sub == "off":
                self._monitor_runner.enabled = False
                return ("Monitors disabled.", None, False, None)
            names = self._monitor_runner.monitor_names()
            status = "enabled" if self._monitor_runner.enabled else "disabled"
            if not names:
                return (f"Monitors: {status}. No monitors registered.", None, False, None)
            return (f"Monitors: {status}\nActive: {', '.join(names)}", None, False, None)
```

3. Add to `/help` output:

```python
"/bg <prompt> — run a prompt in the background",
"/jobs — list background jobs",
"/job <id> — show job status and result",
"/job cancel <id> — cancel a job",
"/delegate <agent> <prompt> — delegate a task to another agent",
"/monitors — show system monitor status",
"/monitors on / off — enable or disable monitors",
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_job_commands.py -v`
Expected: All 11 tests PASS

- [ ] **Step 4: Run full suite**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add app/commands.py tests/test_job_commands.py
git commit -m "feat: add /bg, /jobs, /job, /delegate, /monitors commands"
```

---

### Task 5: Wire JobRunner and MonitorRunner into router

**Files:**
- Modify: `app/router.py`

- [ ] **Step 1: Add imports**

Add near the top of router.py with other imports:

```python
from .job_store import JobStore
from .job_runner import JobRunner
from .monitors import MonitorRunner, disk_usage_monitor, process_count_monitor
```

- [ ] **Step 2: Initialize in router setup**

In the `_setup()` method (around where scheduler is initialized, lines 218-240), add after the scheduler setup:

```python
        # Background job system
        self._job_store = JobStore(get_state_dir() / "jobs.db")
        self._job_runner = JobRunner(
            job_store=self._job_store,
            model_runner=self._model_runner,
            agents_dir=self._config.agents_dir,
        )
        for account_id, account_runtime in self._account_runtimes.items():
            ch = account_runtime.channel
            platform = account_runtime.account.platform
            self._job_runner.register_sender(f"{platform}:{account_id}", _make_sender(ch))

        # System monitors
        self._monitor_runner = MonitorRunner()
        self._monitor_runner.register_monitor("disk_usage", disk_usage_monitor())
        self._monitor_runner.register_monitor("process_count", process_count_monitor())
        for account_id, account_runtime in self._account_runtimes.items():
            ch = account_runtime.channel
            platform = account_runtime.account.platform
            key = f"{platform}:{account_id}"
            self._monitor_runner.register_sender(key, _make_sender(ch))
            for cid in account_runtime.account.allowed_chat_ids:
                self._monitor_runner.register_target(key, cid)
```

- [ ] **Step 3: Pass to CommandHandler**

In the CommandHandler initialization (search for `self._commands = CommandHandler`), add:

```python
            job_store=self._job_store,
            job_runner=self._job_runner,
            monitor_runner=self._monitor_runner,
```

- [ ] **Step 4: Start/stop in lifecycle**

In the `run()` method, after `self._scheduler.start()`, add:

```python
        self._job_runner.start()
        self._monitor_runner.start()
```

In the shutdown section (search for `self._scheduler.stop()`), add:

```python
            self._job_runner.stop()
            self._monitor_runner.stop()
```

- [ ] **Step 5: Run all tests**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add app/router.py
git commit -m "feat: wire JobRunner and MonitorRunner into router lifecycle"
```

---

### Task 6: Full test suite verification

- [ ] **Step 1: Run entire test suite**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest -v`
Expected: All tests pass

- [ ] **Step 2: Verify imports**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -c "from app.job_store import JobStore, Job; from app.job_runner import JobRunner; from app.monitors import MonitorRunner, disk_usage_monitor, process_count_monitor; print('Phase 4 imports OK')"`
Expected: `Phase 4 imports OK`
