from __future__ import annotations

import json
from pathlib import Path

from app.doctor import run_doctor


def write_config(config_path: Path, project_root: Path, *, default_agent: str = "main", chat_agent_map: dict[str, str] | None = None) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(
            {
                "telegram_bot_token": "token",
                "allowed_chat_ids": ["123"],
                "default_agent": default_agent,
                "claude_timeout_seconds": 300,
                "telegram_poll_timeout_seconds": 30,
                "typing_interval_seconds": 4,
                "project_root": str(project_root),
                "agents_dir": str(project_root / "agents"),
                "shared_dir": str(project_root / "shared"),
                "claude_working_directory_mode": "agent_dir",
                "model_provider": "claude-code",
                "claude_model": "sonnet",
                "claude_effort": "medium",
                "chat_agent_map": chat_agent_map or {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_doctor_reports_missing_config(tmp_path: Path) -> None:
    checks = run_doctor(tmp_path / "config" / "config.json")
    assert checks[0].status == "fail"
    assert "Config file missing" in checks[0].message
    assert any("Canonical config path" in check.message for check in checks)


def test_doctor_reports_missing_default_agent(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    (project_root / "agents").mkdir(parents=True)
    (project_root / "shared").mkdir(parents=True)
    config_path = project_root / "config" / "config.json"
    write_config(config_path, project_root, default_agent="main")

    checks = run_doctor(config_path)

    messages = [check.message for check in checks]
    assert any("Account primary default agent missing: main" in message for message in messages)
    assert any("Runtime PID path:" in message for message in messages)
    assert any("Runtime log path:" in message for message in messages)


def test_doctor_warns_on_missing_routing_target(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    (project_root / "agents" / "main").mkdir(parents=True)
    (project_root / "shared").mkdir(parents=True)
    config_path = project_root / "config" / "config.json"
    write_config(config_path, project_root, chat_agent_map={"123": "builder"})

    checks = run_doctor(config_path)

    messages = [check.message for check in checks]
    assert any("Account primary chat 123 routes to missing agent: builder" in message for message in messages)
    assert any("Agents path:" in message for message in messages)


def test_doctor_checks_pymupdf(tmp_path: Path) -> None:
    """Doctor should report pymupdf status."""
    project_root = tmp_path / "project"
    (project_root / "agents" / "main").mkdir(parents=True)
    (project_root / "shared").mkdir(parents=True)
    config_path = project_root / "config" / "config.json"
    write_config(config_path, project_root)

    checks = run_doctor(config_path)
    names = [c.name for c in checks]
    assert "pymupdf" in names


def test_doctor_checks_pyautogui(tmp_path: Path) -> None:
    """Doctor should report pyautogui status."""
    project_root = tmp_path / "project"
    (project_root / "agents" / "main").mkdir(parents=True)
    (project_root / "shared").mkdir(parents=True)
    config_path = project_root / "config" / "config.json"
    write_config(config_path, project_root)

    checks = run_doctor(config_path)
    names = [c.name for c in checks]
    assert "pyautogui" in names
