from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.pairing import PairingStore


def test_request_generates_six_digit_code(tmp_path: Path) -> None:
    store = PairingStore(tmp_path)
    result = store.request("acct1", "chat1")

    assert result is not None
    msg, code = result
    assert 100_000 <= code <= 999_999
    assert str(code) in msg


def test_request_rate_limits_same_chat(tmp_path: Path, monkeypatch: Any) -> None:
    """Second request for the same account+chat within 5 min returns None."""
    store = PairingStore(tmp_path)

    # First request succeeds
    result1 = store.request("acct1", "chat1")
    assert result1 is not None

    # Second request is rate-limited
    result2 = store.request("acct1", "chat1")
    assert result2 is None


def test_request_allows_different_chats(tmp_path: Path) -> None:
    """Different chat IDs are not rate-limited against each other."""
    store = PairingStore(tmp_path)

    result1 = store.request("acct1", "chat1")
    result2 = store.request("acct1", "chat2")

    assert result1 is not None
    assert result2 is not None


def test_pending_filters_expired_entries(tmp_path: Path, monkeypatch: Any) -> None:
    """Expired entries are excluded from pending()."""
    store = PairingStore(tmp_path)

    # Create a request at time 1000
    monkeypatch.setattr("app.pairing.time.time", lambda: 1000.0)
    store.request("acct1", "chat1")

    # At time 1000 it should be pending
    assert len(store.pending()) == 1

    # At time 2000 (1000s later, past 600s expiry) it should be gone
    monkeypatch.setattr("app.pairing.time.time", lambda: 2000.0)
    assert len(store.pending()) == 0


def test_approve_valid_code(tmp_path: Path, monkeypatch: Any) -> None:
    """Approving a valid, non-expired code returns (account_id, chat_id)."""
    store = PairingStore(tmp_path)

    monkeypatch.setattr("app.pairing.random.randint", lambda a, b: 123456)
    store.request("acct1", "chat1")

    result = store.approve(123456)
    assert result == ("acct1", "chat1")


def test_approve_wrong_code_returns_none(tmp_path: Path) -> None:
    store = PairingStore(tmp_path)
    store.request("acct1", "chat1")

    result = store.approve(999999)
    assert result is None


def test_approve_expired_code_returns_none(tmp_path: Path, monkeypatch: Any) -> None:
    """Code that has expired cannot be approved."""
    store = PairingStore(tmp_path)

    monkeypatch.setattr("app.pairing.random.randint", lambda a, b: 123456)
    monkeypatch.setattr("app.pairing.time.time", lambda: 1000.0)
    store.request("acct1", "chat1")

    # Jump past expiry (600s)
    monkeypatch.setattr("app.pairing.time.time", lambda: 2000.0)
    result = store.approve(123456)
    assert result is None


def test_poll_approved_returns_and_clears(tmp_path: Path, monkeypatch: Any) -> None:
    """poll_approved returns approved pairs and clears the file."""
    store = PairingStore(tmp_path)

    monkeypatch.setattr("app.pairing.random.randint", lambda a, b: 123456)
    store.request("acct1", "chat1")
    store.approve(123456)

    pairs = store.poll_approved()
    assert pairs == [("acct1", "chat1")]

    # Second poll returns empty — file was cleared
    pairs2 = store.poll_approved()
    assert pairs2 == []


def test_poll_approved_handles_missing_file(tmp_path: Path) -> None:
    """poll_approved returns empty list when no approved file exists."""
    store = PairingStore(tmp_path)
    assert store.poll_approved() == []


def test_poll_approved_handles_corrupt_json(tmp_path: Path) -> None:
    """poll_approved recovers gracefully from corrupt JSON."""
    store = PairingStore(tmp_path)
    store._approved_path.parent.mkdir(parents=True, exist_ok=True)
    store._approved_path.write_text("not valid json{{{", encoding="utf-8")

    assert store.poll_approved() == []
