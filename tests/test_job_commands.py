from __future__ import annotations

from pathlib import Path
from app.commands import CommandHandler
from app.job_store import JobStore
from app.monitors import MonitorRunner
from app.runtime_state import RuntimeState


def _make_handler(tmp_path, job_store=None, monitor_runner=None):
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)
    (agents_dir / "builder").mkdir(parents=True)
    return CommandHandler(
        agents_dir=agents_dir,
        job_store=job_store,
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
    assert "queued" in reply.lower()
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
    assert "No jobs" in reply


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
    assert "delegated" in reply.lower()
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
    assert "unknown" in reply.lower() or "Unknown" in reply


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
