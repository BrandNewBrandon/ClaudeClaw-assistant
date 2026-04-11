from __future__ import annotations

from pathlib import Path
import pytest
from app.scheduler import Scheduler, SchedulerError, TaskStore
from app.commands import CommandHandler
from app.runtime_state import RuntimeState


def _make_scheduler(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    return Scheduler(store)


def _make_handler(tmp_path, scheduler=None):
    agents_dir = tmp_path / "agents"
    (agents_dir / "main").mkdir(parents=True)
    return CommandHandler(agents_dir=agents_dir, scheduler=scheduler)


def test_send_to_dispatches_to_registered_callback(tmp_path):
    scheduler = _make_scheduler(tmp_path)
    sent = []
    scheduler.register_sender("telegram:primary", lambda s, c, t: sent.append((s, c, t)))
    scheduler.send_to("telegram:primary", "12345", "hello")
    assert sent == [("telegram:primary", "12345", "hello")]


def test_send_to_raises_for_unregistered_surface(tmp_path):
    scheduler = _make_scheduler(tmp_path)
    with pytest.raises(SchedulerError, match="No sender registered"):
        scheduler.send_to("unknown:surface", "12345", "hello")


def test_forward_full_target(tmp_path):
    scheduler = _make_scheduler(tmp_path)
    sent = []
    scheduler.register_sender("telegram:primary", lambda s, c, t: sent.append((s, c, t)))
    handler = _make_handler(tmp_path, scheduler=scheduler)
    reply, _, _, _ = handler.handle(
        "/forward telegram:primary:99999 Hello there",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
        surface="telegram:primary", chat_id="12345",
    )
    assert "Forwarded" in reply
    assert sent == [("telegram:primary", "99999", "Hello there")]


def test_forward_short_target(tmp_path):
    scheduler = _make_scheduler(tmp_path)
    sent = []
    scheduler.register_sender("telegram:primary", lambda s, c, t: sent.append((s, c, t)))
    handler = _make_handler(tmp_path, scheduler=scheduler)
    reply, _, _, _ = handler.handle(
        "/forward 99999 Hello short",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
        surface="telegram:primary", chat_id="12345",
    )
    assert "Forwarded" in reply
    assert sent == [("telegram:primary", "99999", "Hello short")]


def test_forward_no_scheduler(tmp_path):
    handler = _make_handler(tmp_path, scheduler=None)
    reply, _, _, _ = handler.handle(
        "/forward 99999 Hi",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
    )
    assert "not available" in reply.lower()


def test_forward_missing_message(tmp_path):
    scheduler = _make_scheduler(tmp_path)
    handler = _make_handler(tmp_path, scheduler=scheduler)
    reply, _, _, _ = handler.handle(
        "/forward 99999",
        active_agent="main", default_agent="main", runtime_state=RuntimeState(),
        surface="telegram:primary", chat_id="12345",
    )
    assert "Usage" in reply
