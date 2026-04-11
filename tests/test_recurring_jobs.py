from __future__ import annotations
from pathlib import Path
from app.job_store import JobStore


def test_create_recurring_job(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(
        chat_id="c1", account_id="primary", surface="s",
        agent="main", prompt="check stuff", recurrence_seconds=3600,
    )
    job = store.get_job(job_id)
    assert job is not None
    assert job.recurrence_seconds == 3600


def test_non_recurring_job_has_none(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(
        chat_id="c1", account_id="primary", surface="s",
        agent="main", prompt="one shot",
    )
    job = store.get_job(job_id)
    assert job is not None
    assert job.recurrence_seconds is None


def test_every_command_creates_recurring(tmp_path: Path) -> None:
    from app.commands import CommandHandler
    from app.runtime_state import RuntimeState
    store = JobStore(tmp_path / "jobs.db")
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)
    handler = CommandHandler(agents_dir=agents_dir, job_store=store)
    reply, _, _, _ = handler.handle(
        "/every 24h check github",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
        surface="telegram:primary", chat_id="c1", account_id="primary",
    )
    assert "recurring" in reply.lower() or "every" in reply.lower()
    jobs = store.list_jobs("c1")
    assert len(jobs) == 1
    assert jobs[0].recurrence_seconds == 86400


def test_every_command_invalid_interval(tmp_path: Path) -> None:
    from app.commands import CommandHandler
    from app.runtime_state import RuntimeState
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)
    store = JobStore(tmp_path / "jobs.db")
    handler = CommandHandler(agents_dir=agents_dir, job_store=store)
    reply, _, _, _ = handler.handle(
        "/every xyz do stuff",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
        surface="s", chat_id="c1",
    )
    assert "invalid" in reply.lower() or "Invalid" in reply
