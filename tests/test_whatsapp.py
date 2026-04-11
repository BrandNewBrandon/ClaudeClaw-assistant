"""Tests for WhatsApp channel adapter."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import BytesIO

import pytest

from app.channels.whatsapp_channel import WhatsAppChannel
from app.channels.base import ChannelError


def _mock_urlopen(response_data: dict, status: int = 200):
    """Create a mock for urllib.request.urlopen."""
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)
    return mock_response


def test_whatsapp_send_message():
    """send_message should POST to bridge /send endpoint."""
    ch = WhatsAppChannel(
        bot_token="test-key",
        allowed_chat_ids=["+1555"],
        bridge_url="http://localhost:3000",
    )
    mock_resp = _mock_urlopen({"ok": True})
    with patch("app.channels.whatsapp_channel.urllib.request.urlopen", return_value=mock_resp) as mock_open:
        ch.send_message("+1555", "Hello!")
    mock_open.assert_called_once()
    req = mock_open.call_args[0][0]
    assert req.full_url == "http://localhost:3000/send"
    assert req.method == "POST"
    body = json.loads(req.data.decode("utf-8"))
    assert body["to"] == "+1555"
    assert body["text"] == "Hello!"


def test_whatsapp_send_includes_auth_header():
    """Requests should include Authorization header."""
    ch = WhatsAppChannel(
        bot_token="my-secret-key",
        allowed_chat_ids=["+1555"],
        bridge_url="http://localhost:3000",
    )
    mock_resp = _mock_urlopen({"ok": True})
    with patch("app.channels.whatsapp_channel.urllib.request.urlopen", return_value=mock_resp) as mock_open:
        ch.send_message("+1555", "Hi")
    req = mock_open.call_args[0][0]
    assert req.get_header("Authorization") == "Bearer my-secret-key"


def test_whatsapp_polls_messages():
    """_check_new_messages should queue messages from bridge."""
    ch = WhatsAppChannel(
        bot_token="key",
        allowed_chat_ids=["+15551234567"],
        bridge_url="http://localhost:3000",
    )
    response = {
        "messages": [
            {"id": "msg1", "from": "+15551234567", "text": "Hello", "timestamp": "2026-04-11T14:30:00Z"},
        ]
    }
    mock_resp = _mock_urlopen(response)
    with patch("app.channels.whatsapp_channel.urllib.request.urlopen", return_value=mock_resp):
        ch._check_new_messages()

    msg = ch._queue.get_nowait()
    assert msg.text == "Hello"
    assert msg.chat_id == "+15551234567"


def test_whatsapp_filters_by_allowed():
    """Should ignore messages from non-allowed contacts."""
    ch = WhatsAppChannel(
        bot_token="key",
        allowed_chat_ids=["+19999999999"],
        bridge_url="http://localhost:3000",
    )
    response = {
        "messages": [
            {"id": "msg1", "from": "+15551234567", "text": "Hello", "timestamp": "2026-04-11T14:30:00Z"},
        ]
    }
    mock_resp = _mock_urlopen(response)
    with patch("app.channels.whatsapp_channel.urllib.request.urlopen", return_value=mock_resp):
        ch._check_new_messages()

    assert ch._queue.empty()


def test_whatsapp_deduplicates_messages():
    """Should not queue the same message twice."""
    ch = WhatsAppChannel(
        bot_token="key",
        allowed_chat_ids=["+1555"],
        bridge_url="http://localhost:3000",
    )
    response = {
        "messages": [
            {"id": "msg1", "from": "+1555", "text": "Hello", "timestamp": "2026-04-11T14:30:00Z"},
        ]
    }
    mock_resp = _mock_urlopen(response)
    with patch("app.channels.whatsapp_channel.urllib.request.urlopen", return_value=mock_resp):
        ch._check_new_messages()
        ch._check_new_messages()  # Same message ID

    count = 0
    while not ch._queue.empty():
        ch._queue.get_nowait()
        count += 1
    assert count == 1


def test_whatsapp_send_empty_skipped():
    """Empty messages should not be sent."""
    ch = WhatsAppChannel(
        bot_token="key",
        allowed_chat_ids=["+1555"],
        bridge_url="http://localhost:3000",
    )
    with patch("app.channels.whatsapp_channel.urllib.request.urlopen") as mock_open:
        ch.send_message("+1555", "")
        ch.send_message("+1555", "   ")
    mock_open.assert_not_called()


def test_whatsapp_seen_ids_bounded():
    """seen_ids set should not grow unbounded."""
    ch = WhatsAppChannel(
        bot_token="key",
        allowed_chat_ids=["+1555"],
        bridge_url="http://localhost:3000",
    )
    # Simulate 10001 seen IDs
    ch._seen_ids = {f"msg-{i}" for i in range(10001)}
    response = {"messages": []}
    mock_resp = _mock_urlopen(response)
    with patch("app.channels.whatsapp_channel.urllib.request.urlopen", return_value=mock_resp):
        ch._check_new_messages()
    assert len(ch._seen_ids) <= 5000
