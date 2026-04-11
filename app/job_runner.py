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
        model_runner: Any,
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
