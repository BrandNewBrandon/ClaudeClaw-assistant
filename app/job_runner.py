"""Background job execution engine."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

from .context_builder import ContextBuilder
from .job_store import JobStore
from .tools import ToolLoop, ToolError, build_default_registry, execute_shell_command, ToolSpec

if TYPE_CHECKING:
    from .memory import MemoryStore

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
        memory_store: "MemoryStore | None" = None,
        semantic_search_enabled: bool = True,
        max_concurrent: int = 2,
        poll_interval: int = 10,
    ) -> None:
        self._store = job_store
        self._model_runner = model_runner
        self._agents_dir = agents_dir
        self._memory = memory_store
        self._semantic_search = semantic_search_enabled
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
        recovered = self._store.recover_stale_jobs()
        if recovered:
            LOGGER.info("Recovered %d stale job(s) from prior crash", recovered)
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
                args=(job.id, job.prompt, job.agent, job.surface, job.chat_id, job.account_id),
                name=f"job-{job.id}",
                daemon=True,
            )
            thread.start()

    def _execute_job(
        self, job_id: str, prompt: str, agent: str, surface: str, chat_id: str,
        account_id: str,
    ) -> None:
        try:
            working_dir = self._agents_dir / agent
            agent_context = self._context_builder.load_agent_context(agent)

            # Load conversation context if memory store available
            recent_transcript: list = []
            relevant_memory: list[str] = []
            if self._memory is not None:
                # Derive surface name for transcript lookup (e.g. "telegram" from "telegram:primary")
                transcript_surface = surface.split(":")[0] if ":" in surface else surface
                recent_transcript = self._memory.read_recent_transcript(
                    transcript_surface, chat_id, limit=10,
                    account_id=account_id, agent_name=agent,
                )
                relevant_memory = self._memory.find_relevant_memory(
                    agent, prompt, limit=4, semantic=self._semantic_search,
                )

            # Build tool registry (no approval gate — background jobs auto-approve safe commands)
            tool_registry = build_default_registry(working_dir)
            from .agent_config import load_agent_config
            agent_cfg = load_agent_config(self._agents_dir / agent)

            def _bg_run_command(args: dict) -> str:
                cmd = str(args.get("command", "")).strip()
                if not cmd:
                    return "command is required."
                # Only allow safe commands in background (no interactive approval)
                if any(cmd == p or cmd.startswith(p + " ") for p in agent_cfg.safe_commands):
                    return execute_shell_command(cmd, cwd=str(working_dir))
                return f"Command '{cmd}' requires approval and cannot run in background jobs. Only safe commands are allowed: {', '.join(agent_cfg.safe_commands) or '(none configured)'}"

            tool_registry.register(
                ToolSpec("run_command", "Run a shell command and return its output.", {"command": "shell command string"}),
                _bg_run_command,
            )

            tool_loop = ToolLoop(tool_registry, max_tool_calls=3)
            tool_results: list[str] = []
            last_output = ""

            for iteration in range(tool_loop.max_tool_calls + 1):
                full_prompt = self._context_builder.build_prompt(
                    agent_context, prompt,
                    recent_transcript=recent_transcript,
                    relevant_memory=relevant_memory,
                    tool_instructions=tool_loop.tool_instructions(),
                    tool_results=tool_results or None,
                )
                result = self._model_runner.run_prompt(
                    prompt=full_prompt,
                    working_directory=working_dir,
                )
                last_output = result.stdout.strip()
                if not last_output:
                    break

                try:
                    tool_call = tool_loop.parse_tool_call(last_output)
                except ToolError:
                    break

                if tool_call is None:
                    break

                tool_result = tool_loop.execute(tool_call)
                tool_results.append(tool_loop.format_tool_result(tool_result))
                LOGGER.info("Job %s tool call: %s ok=%s", job_id, tool_call.name, tool_result.ok)

            output = last_output or "(no response)"
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
