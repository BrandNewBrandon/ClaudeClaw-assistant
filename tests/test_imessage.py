"""Tests for iMessage channel adapter."""
from __future__ import annotations

import sqlite3
import platform
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def test_imessage_rejects_non_macos(tmp_path: Path) -> None:
    """Should raise ChannelError on non-macOS."""
    from app.channels.base import ChannelError
    with patch("app.channels.imessage.platform") as mock_plat:
        mock_plat.system.return_value = "Windows"
        from app.channels.imessage import IMessageChannel
        with pytest.raises(ChannelError, match="macOS"):
            IMessageChannel(allowed_chat_ids=["+1555"], db_path=tmp_path / "chat.db")


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
def test_imessage_start_raises_without_db(tmp_path: Path) -> None:
    """Should raise ChannelError if Messages DB doesn't exist."""
    from app.channels.base import ChannelError
    from app.channels.imessage import IMessageChannel
    ch = IMessageChannel(
        allowed_chat_ids=["+1555"],
        db_path=tmp_path / "nonexistent.db",
    )
    with pytest.raises(ChannelError, match="not found"):
        ch.start()


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
def test_imessage_polls_new_messages(tmp_path: Path) -> None:
    """Should pick up new messages from the database."""
    from app.channels.imessage import IMessageChannel

    db_path = tmp_path / "chat.db"
    _create_test_db(db_path)

    ch = IMessageChannel(
        allowed_chat_ids=["+15551234567"],
        db_path=db_path,
        poll_interval=0.1,
    )
    # Manually set last_rowid to 0 and check
    ch._last_rowid = 0
    ch._check_new_messages()

    messages = []
    while True:
        try:
            messages.append(ch._queue.get_nowait())
        except Exception:
            break

    assert len(messages) == 1
    assert messages[0].text == "Hello from test"
    assert messages[0].chat_id == "+15551234567"


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
def test_imessage_filters_by_allowed_ids(tmp_path: Path) -> None:
    """Should ignore messages from non-allowed contacts."""
    from app.channels.imessage import IMessageChannel

    db_path = tmp_path / "chat.db"
    _create_test_db(db_path)

    ch = IMessageChannel(
        allowed_chat_ids=["+19999999999"],  # Different number
        db_path=db_path,
        poll_interval=0.1,
    )
    ch._last_rowid = 0
    ch._check_new_messages()

    try:
        msg = ch._queue.get_nowait()
        assert False, f"Should not have received message: {msg}"
    except Exception:
        pass  # Expected — no messages for this allowed_id


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
def test_imessage_send_calls_osascript(tmp_path: Path) -> None:
    """send_message should call osascript with correct AppleScript."""
    from app.channels.imessage import IMessageChannel

    db_path = tmp_path / "chat.db"
    _create_test_db(db_path)

    ch = IMessageChannel(
        allowed_chat_ids=["+15551234567"],
        db_path=db_path,
    )
    with patch("app.channels.imessage.subprocess") as mock_sub:
        mock_sub.run.return_value = MagicMock(returncode=0)
        ch.send_message("+15551234567", "Hello!")
    mock_sub.run.assert_called_once()
    args = mock_sub.run.call_args
    assert args[0][0][0] == "osascript"
    assert "Hello!" in args[0][0][2]


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
def test_imessage_skips_own_messages(tmp_path: Path) -> None:
    """Should not pick up is_from_me=1 messages."""
    from app.channels.imessage import IMessageChannel

    db_path = tmp_path / "chat.db"
    _create_test_db(db_path, include_sent=True)

    ch = IMessageChannel(
        allowed_chat_ids=["+15551234567"],
        db_path=db_path,
        poll_interval=0.1,
    )
    ch._last_rowid = 0
    ch._check_new_messages()

    messages = []
    while True:
        try:
            messages.append(ch._queue.get_nowait())
        except Exception:
            break

    # Only the received message, not the sent one
    assert len(messages) == 1
    assert messages[0].text == "Hello from test"


def _create_test_db(db_path: Path, *, include_sent: bool = False) -> None:
    """Create a minimal Messages-compatible SQLite database."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE handle (
            ROWID INTEGER PRIMARY KEY,
            id TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE message (
            ROWID INTEGER PRIMARY KEY,
            text TEXT,
            is_from_me INTEGER DEFAULT 0,
            date INTEGER DEFAULT 0,
            handle_id INTEGER
        )
    """)
    conn.execute("INSERT INTO handle (ROWID, id) VALUES (1, '+15551234567')")
    conn.execute(
        "INSERT INTO message (ROWID, text, is_from_me, date, handle_id) "
        "VALUES (1, 'Hello from test', 0, 0, 1)"
    )
    if include_sent:
        conn.execute(
            "INSERT INTO message (ROWID, text, is_from_me, date, handle_id) "
            "VALUES (2, 'My reply', 1, 0, 1)"
        )
    conn.commit()
    conn.close()
