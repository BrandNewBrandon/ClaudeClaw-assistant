from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import monotonic


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


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()
