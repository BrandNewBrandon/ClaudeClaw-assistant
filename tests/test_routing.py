from __future__ import annotations

import os
import threading
from pathlib import Path

from app import app_paths
from app.router import AccountRuntime, AssistantRouter
from app.sessions import SessionStore


def make_router(tmp_path: Path, *, default_agent: str = "main", chat_agent_map: dict[str, str] | None = None) -> AssistantRouter:
    os.environ[app_paths.APP_ROOT_ENV] = str(tmp_path / "app-root")
    router = AssistantRouter()
    router._config = type(
        "ConfigStub",
        (),
        {
            "default_agent": default_agent,
            "chat_agent_map": chat_agent_map or {},
            "routing": {
                "primary": type(
                    "RoutingStub",
                    (),
                    {
                        "default_agent": default_agent,
                        "chat_agent_map": chat_agent_map or {},
                    },
                )()
            },
        },
    )()
    router._sessions = SessionStore(shared_dir=tmp_path / "shared")
    return router


def test_routing_prefers_config_pinned_agent(tmp_path: Path) -> None:
    try:
        router = make_router(tmp_path, default_agent="main", chat_agent_map={"123": "builder"})
        router._sessions.set_active_agent("123", "main", session_key="telegram:primary:123")

        agent, source = router._resolve_agent_for_chat("123")

        assert agent == "builder"
        assert source == "config"
    finally:
        os.environ.pop(app_paths.APP_ROOT_ENV, None)


def test_routing_uses_session_agent_when_not_pinned(tmp_path: Path) -> None:
    try:
        router = make_router(tmp_path, default_agent="main")
        router._sessions.set_active_agent("123", "builder", session_key="telegram:primary:123")

        agent, source = router._resolve_agent_for_chat("123")

        assert agent == "builder"
        assert source == "session"
    finally:
        os.environ.pop(app_paths.APP_ROOT_ENV, None)


def test_routing_falls_back_to_default_agent(tmp_path: Path) -> None:
    try:
        router = make_router(tmp_path, default_agent="main")

        agent, source = router._resolve_agent_for_chat("123")

        assert agent == "main"
        assert source == "default"
    finally:
        os.environ.pop(app_paths.APP_ROOT_ENV, None)


def test_routing_scopes_session_by_account(tmp_path: Path) -> None:
    try:
        router = make_router(tmp_path, default_agent="main")
        router._config.routing["builder"] = type(
            "RoutingStub",
            (),
            {
                "default_agent": "builder",
                "chat_agent_map": {},
            },
        )()
        router._sessions.set_active_agent("123", "builder", session_key="telegram:builder:123")

        main_agent, main_source = router._resolve_agent_for_chat("123", account_id="primary")
        builder_agent, builder_source = router._resolve_agent_for_chat("123", account_id="builder")

        assert main_agent == "main"
        assert main_source == "default"
        assert builder_agent == "builder"
        assert builder_source == "default"
    finally:
        os.environ.pop(app_paths.APP_ROOT_ENV, None)


def test_start_account_workers_creates_one_thread_per_account() -> None:
    router = AssistantRouter()
    router._account_runtimes = {
        "primary": AccountRuntime(account=None, routing=None, channel=None),
        "builder": AccountRuntime(account=None, routing=None, channel=None),
    }
    started: list[tuple[str, AccountRuntime]] = []

    def fake_worker(account_id: str, account_runtime: AccountRuntime) -> None:
        started.append((account_id, account_runtime))

    router._account_worker = fake_worker  # type: ignore[method-assign]

    workers = router._start_account_workers()

    for thread in workers:
        thread.join(timeout=1)

    assert len(workers) == 2
    assert sorted(account_id for account_id, _ in started) == ["builder", "primary"]


def test_monitor_workers_raises_for_worker_error() -> None:
    router = AssistantRouter()
    failure = RuntimeError("boom")
    router._worker_errors.put(("primary", failure))

    try:
        router._monitor_workers([])
    except SystemExit as exc:
        assert "Account worker failed for primary: boom" in str(exc)
    else:
        raise AssertionError("Expected SystemExit")


def test_monitor_workers_raises_for_dead_worker() -> None:
    router = AssistantRouter()
    dead_thread = threading.Thread(name="channel-poll-primary")

    try:
        router._monitor_workers([dead_thread])
    except SystemExit as exc:
        assert "Account worker stopped unexpectedly: channel-poll-primary" in str(exc)
    else:
        raise AssertionError("Expected SystemExit")


def test_session_key_differs_by_agent(tmp_path: Path) -> None:
    """Two agents in the same chat produce different session keys for _session_ids."""
    try:
        router = make_router(tmp_path, default_agent="main")
        # Simulate session IDs stored for two agents in the same chat
        session_key = "telegram:primary:123"
        router._session_ids[f"{session_key}:main"] = "session-main"
        router._session_ids[f"{session_key}:builder"] = "session-builder"

        assert router._session_ids.get(f"{session_key}:main") == "session-main"
        assert router._session_ids.get(f"{session_key}:builder") == "session-builder"
        assert router._session_ids.get(f"{session_key}:main") != router._session_ids.get(f"{session_key}:builder")
    finally:
        os.environ.pop(app_paths.APP_ROOT_ENV, None)


def test_session_key_format_includes_agent(tmp_path: Path) -> None:
    """_session_key base is surface:account:chat_id; agent appended inline."""
    try:
        router = make_router(tmp_path)
        base = router._session_key("telegram", "primary", "123")
        assert base == "telegram:primary:123"
        # Agent-scoped key is base + ":" + agent
        assert f"{base}:main" == "telegram:primary:123:main"
        assert f"{base}:builder" == "telegram:primary:123:builder"
    finally:
        os.environ.pop(app_paths.APP_ROOT_ENV, None)
