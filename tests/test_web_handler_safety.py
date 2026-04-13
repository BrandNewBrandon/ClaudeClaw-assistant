"""Tests for dashboard HTTP handler exception safety.

The dashboard HTTP server runs in a background thread inside the runtime
process. An unhandled exception in a request handler would otherwise kill
the connection mid-response and hang the browser tab. The handler now wraps
do_GET / do_POST in a last-resort try/except that logs the traceback and
sends a 500 JSON body — and critically, the server thread stays alive so
subsequent requests still work.
"""
from __future__ import annotations

import json
import socket
import threading
import urllib.request
from http.client import HTTPResponse
from pathlib import Path

import pytest

from app.web import server as web_server


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def running_dashboard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Spin up a WebDashboard on an ephemeral port, bound to tmp_path for state."""
    # Point app-root at tmp_path so the dashboard doesn't touch real state.
    monkeypatch.setenv("ASSISTANT_APP_ROOT", str(tmp_path))
    # Config file used by _load_config — empty dict disables dashboard_token.
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text("{}", encoding="utf-8")

    port = _find_free_port()
    dashboard = web_server.WebDashboard(
        host="127.0.0.1",
        port=port,
        agents_dir=tmp_path / "agents",
        shared_dir=tmp_path / "shared",
    )
    (tmp_path / "agents").mkdir()
    (tmp_path / "shared").mkdir()

    dashboard.start(blocking=False)
    # Give the thread a moment to bind.
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                break
        except OSError:
            threading.Event().wait(0.05)
    else:
        dashboard.stop()
        pytest.fail("Dashboard did not come up")

    yield dashboard, port
    dashboard.stop()


def _get(port: int, path: str) -> tuple[int, dict]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
    try:
        resp: HTTPResponse = urllib.request.urlopen(req, timeout=5)
        return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_handler_returns_500_when_api_raises(
    running_dashboard, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, port = running_dashboard
    monkeypatch.setattr(
        web_server, "_api_status", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    status, body = _get(port, "/api/status")
    assert status == 500
    assert body == {"error": "internal server error"}


def test_handler_thread_survives_handler_exception(
    running_dashboard, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After a handler raises, a later request must still succeed."""
    _, port = running_dashboard
    monkeypatch.setattr(
        web_server, "_api_status", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    # Trigger the crash.
    status, _ = _get(port, "/api/status")
    assert status == 500
    # Unpatch — _api_status returns a real dict again.
    monkeypatch.undo()
    # The dashboard thread must still be alive and serving.
    status, body = _get(port, "/api/status")
    assert status == 200
    assert "running" in body
