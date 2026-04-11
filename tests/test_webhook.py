from __future__ import annotations
from pathlib import Path
from app.job_store import JobStore


def test_webhook_creates_job(tmp_path: Path) -> None:
    """Webhook should create a job in the database."""
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(
        chat_id="webhook", account_id="primary", surface="",
        agent="main", prompt="external trigger: deploy complete",
    )
    job = store.get_job(job_id)
    assert job is not None
    assert job.prompt == "external trigger: deploy complete"
    assert job.chat_id == "webhook"
