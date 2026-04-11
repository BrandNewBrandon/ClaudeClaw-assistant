from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import monotonic
from typing import Any


@dataclass
class RuntimeState:
    process_id: int | None = None
    started_at: str | None = None
    last_message_at: str | None = None
    last_error: str | None = None
    config_path: str | None = None
    lock_path: str | None = None
    transcript_path: str | None = None
    account_id: str | None = None
    active_agent: str | None = None
    active_agent_display_name: str | None = None
    active_agent_description: str | None = None
    routing_source: str | None = None
    claude_model: str | None = None
    claude_effort: str | None = None
    current_message_started_monotonic: float | None = None
    current_message_id: int | None = None
    typing_started_at: str | None = None
    model_started_at: str | None = None
    model_finished_at: str | None = None
    last_reply_at: str | None = None
    last_message_duration_ms: int | None = None
    last_model_duration_ms: int | None = None

    # Thread health tracking
    messages_processed: int = 0
    tool_calls_executed: int = 0
    errors_count: int = 0
    active_threads: dict[str, str] = None  # name -> status

    def __post_init__(self) -> None:
        if self.active_threads is None:
            self.active_threads = {}

    def mark_started(
        self,
        *,
        process_id: int,
        config_path: Path,
        lock_path: Path,
        claude_model: str | None,
        claude_effort: str | None,
    ) -> None:
        self.process_id = process_id
        self.started_at = _now_iso()
        self.config_path = str(config_path)
        self.lock_path = str(lock_path)
        self.claude_model = claude_model
        self.claude_effort = claude_effort

    def mark_message(self, *, message_id: int | None = None) -> None:
        self.last_message_at = _now_iso()
        self.current_message_started_monotonic = monotonic()
        self.current_message_id = message_id
        self.typing_started_at = None
        self.model_started_at = None
        self.model_finished_at = None

    def mark_typing_started(self) -> None:
        self.typing_started_at = _now_iso()

    def mark_model_started(self) -> None:
        self.model_started_at = _now_iso()

    def mark_model_finished(self) -> None:
        self.model_finished_at = _now_iso()
        if self.current_message_started_monotonic is None:
            return
        self.last_model_duration_ms = int((monotonic() - self.current_message_started_monotonic) * 1000)

    def set_last_model_duration_ms(self, duration_ms: int) -> None:
        self.last_model_duration_ms = duration_ms

    def mark_reply_sent(self) -> None:
        self.last_reply_at = _now_iso()
        if self.current_message_started_monotonic is None:
            return
        self.last_message_duration_ms = int((monotonic() - self.current_message_started_monotonic) * 1000)

    def mark_error(self, message: str) -> None:
        self.last_error = message

    def set_transcript_path(self, path: Path) -> None:
        self.transcript_path = str(path)

    def set_active_agent(
        self,
        agent_name: str,
        *,
        account_id: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        routing_source: str | None = None,
    ) -> None:
        self.account_id = account_id
        self.active_agent = agent_name
        self.active_agent_display_name = display_name
        self.active_agent_description = description
        self.routing_source = routing_source

    def increment_messages(self) -> None:
        self.messages_processed += 1

    def increment_tool_calls(self) -> None:
        self.tool_calls_executed += 1

    def increment_errors(self) -> None:
        self.errors_count += 1

    def register_thread(self, name: str, status: str = "running") -> None:
        self.active_threads[name] = status

    def unregister_thread(self, name: str) -> None:
        self.active_threads.pop(name, None)

    def get_diagnostics(self) -> dict[str, Any]:
        """Return a snapshot of runtime diagnostics."""
        return {
            "process_id": self.process_id,
            "started_at": self.started_at,
            "last_message_at": self.last_message_at,
            "messages_processed": self.messages_processed,
            "tool_calls_executed": self.tool_calls_executed,
            "errors_count": self.errors_count,
            "last_error": self.last_error,
            "active_agent": self.active_agent,
            "claude_model": self.claude_model,
            "claude_effort": self.claude_effort,
            "last_model_duration_ms": self.last_model_duration_ms,
            "last_message_duration_ms": self.last_message_duration_ms,
            "active_threads": dict(self.active_threads),
        }


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()
