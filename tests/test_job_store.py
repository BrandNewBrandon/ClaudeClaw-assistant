from __future__ import annotations
from pathlib import Path
from app.job_store import JobStore, Job


def test_create_job_returns_id(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(chat_id="c1", account_id="primary", surface="telegram:primary", agent="main", prompt="do something")
    assert isinstance(job_id, str)
    assert len(job_id) == 8

def test_get_job_returns_created_job(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(chat_id="c1", account_id="primary", surface="telegram:primary", agent="main", prompt="do something")
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
    job_id = store.create_job(chat_id="c1", account_id="primary", surface="telegram:primary", agent="main", prompt="task")
    job = store.claim_next_pending()
    assert job is not None
    assert job.id == job_id
    assert job.status == "running"
    assert store.claim_next_pending() is None

def test_complete_job(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(chat_id="c1", account_id="primary", surface="telegram:primary", agent="main", prompt="task")
    store.claim_next_pending()
    store.complete_job(job_id, result="done!")
    job = store.get_job(job_id)
    assert job is not None
    assert job.status == "completed"
    assert job.result == "done!"

def test_fail_job(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(chat_id="c1", account_id="primary", surface="telegram:primary", agent="main", prompt="task")
    store.claim_next_pending()
    store.fail_job(job_id, error="timeout")
    job = store.get_job(job_id)
    assert job is not None
    assert job.status == "failed"
    assert job.error == "timeout"

def test_cancel_job(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    job_id = store.create_job(chat_id="c1", account_id="primary", surface="telegram:primary", agent="main", prompt="task")
    assert store.cancel_job(job_id) is True
    job = store.get_job(job_id)
    assert job is not None
    assert job.status == "cancelled"

def test_list_jobs(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    store.create_job(chat_id="c1", account_id="primary", surface="s", agent="main", prompt="a")
    store.create_job(chat_id="c1", account_id="primary", surface="s", agent="main", prompt="b")
    store.create_job(chat_id="c2", account_id="primary", surface="s", agent="main", prompt="c")
    assert len(store.list_jobs("c1")) == 2
    assert len(store.list_jobs()) == 3

def test_running_count(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    store.create_job(chat_id="c1", account_id="primary", surface="s", agent="main", prompt="a")
    store.create_job(chat_id="c1", account_id="primary", surface="s", agent="main", prompt="b")
    assert store.running_count() == 0
    store.claim_next_pending()
    assert store.running_count() == 1
