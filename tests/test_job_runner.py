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


def test_job_runner_processes_pending_job(tmp_path: Path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)

    sent: list[tuple[str, str, str]] = []
    def fake_send(surface, chat_id, text):
        sent.append((surface, chat_id, text))

    runner = JobRunner(
        job_store=store, model_runner=FakeRunner("result text"),
        agents_dir=agents_dir, max_concurrent=2,
    )
    runner.register_sender("telegram:primary", fake_send)

    job_id = store.create_job(
        chat_id="c1", account_id="primary", surface="telegram:primary",
        agent="main", prompt="do something",
    )
    runner.tick()
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
        job_store=store, model_runner=FakeRunner("ok"),
        agents_dir=agents_dir, max_concurrent=1,
    )
    runner.register_sender("s", lambda s, c, t: None)

    store.create_job(chat_id="c1", account_id="primary", surface="s", agent="main", prompt="a")
    store.create_job(chat_id="c1", account_id="primary", surface="s", agent="main", prompt="b")

    runner.tick()
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
        job_store=store, model_runner=ErrorRunner(),
        agents_dir=agents_dir, max_concurrent=2,
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
