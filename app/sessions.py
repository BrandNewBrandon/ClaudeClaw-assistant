from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .app_paths import ensure_runtime_dirs, get_sessions_state_file


@dataclass(frozen=True)
class ChatSessionState:
    active_agent: str


class SessionStore:
    def __init__(self, shared_dir: Path) -> None:
        self._state_path = get_sessions_state_file()
        ensure_runtime_dirs()

    def get_active_agent(self, chat_id: str, default_agent: str, *, session_key: str | None = None) -> str:
        data = self._load_all()
        chat_state = data.get(self._state_key(chat_id, session_key=session_key))
        if isinstance(chat_state, dict):
            active_agent = chat_state.get("active_agent")
            if isinstance(active_agent, str) and active_agent.strip():
                return active_agent
        return default_agent

    def set_active_agent(self, chat_id: str, agent_name: str, *, session_key: str | None = None) -> None:
        data = self._load_all()
        data[self._state_key(chat_id, session_key=session_key)] = {"active_agent": agent_name}
        self._save_all(data)

    def reset_chat(self, chat_id: str, *, session_key: str | None = None) -> None:
        data = self._load_all()
        key = self._state_key(chat_id, session_key=session_key)
        if key in data:
            del data[key]
            self._save_all(data)

    def _load_all(self) -> dict:
        if not self._state_path.exists():
            return {}
        with self._state_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _save_all(self, data: dict) -> None:
        with self._state_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

    @staticmethod
    def _state_key(chat_id: str, *, session_key: str | None = None) -> str:
        return session_key or chat_id
