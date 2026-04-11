from __future__ import annotations

import json
from pathlib import Path

from app.backup import create_backup, restore_backup, list_backup_contents


def test_create_backup_produces_archive(tmp_path: Path, monkeypatch) -> None:
    # Set up fake config/state dirs
    config_dir = tmp_path / "config"
    state_dir = tmp_path / "state"
    (config_dir / "agents" / "main").mkdir(parents=True)
    (config_dir / "config.json").write_text('{"test": true}', encoding="utf-8")
    (config_dir / "agents" / "main" / "AGENT.md").write_text("I am an agent", encoding="utf-8")
    (state_dir / "transcripts").mkdir(parents=True)
    (state_dir / "transcripts" / "chat.jsonl").write_text('{"msg": "hi"}', encoding="utf-8")
    (state_dir / "tasks.db").write_text("fake-db", encoding="utf-8")

    monkeypatch.setattr("app.backup.get_config_dir", lambda: config_dir)
    monkeypatch.setattr("app.backup.get_state_dir", lambda: state_dir)

    output = tmp_path / "backup.tar.gz"
    result = create_backup(output)
    assert result == output
    assert output.exists()
    assert output.stat().st_size > 0


def test_restore_backup_writes_files(tmp_path: Path, monkeypatch) -> None:
    # Create source data
    src_config = tmp_path / "src" / "config"
    src_state = tmp_path / "src" / "state"
    (src_config / "agents" / "main").mkdir(parents=True)
    (src_config / "config.json").write_text('{"restored": true}', encoding="utf-8")
    (src_config / "agents" / "main" / "AGENT.md").write_text("restored agent", encoding="utf-8")
    (src_state).mkdir(parents=True)
    (src_state / "tasks.db").write_text("restored-db", encoding="utf-8")

    monkeypatch.setattr("app.backup.get_config_dir", lambda: src_config)
    monkeypatch.setattr("app.backup.get_state_dir", lambda: src_state)

    archive = tmp_path / "backup.tar.gz"
    create_backup(archive)

    # Restore to different dirs
    dest_config = tmp_path / "dest" / "config"
    dest_state = tmp_path / "dest" / "state"
    monkeypatch.setattr("app.backup.get_config_dir", lambda: dest_config)
    monkeypatch.setattr("app.backup.get_state_dir", lambda: dest_state)

    files = restore_backup(archive)
    assert len(files) >= 3
    assert (dest_config / "config.json").exists()
    assert (dest_config / "config.json").read_text(encoding="utf-8") == '{"restored": true}'
    assert (dest_config / "agents" / "main" / "AGENT.md").read_text(encoding="utf-8") == "restored agent"


def test_dry_run_does_not_write(tmp_path: Path, monkeypatch) -> None:
    src_config = tmp_path / "src" / "config"
    src_state = tmp_path / "src" / "state"
    (src_config).mkdir(parents=True)
    (src_config / "config.json").write_text("{}", encoding="utf-8")
    (src_state).mkdir(parents=True)

    monkeypatch.setattr("app.backup.get_config_dir", lambda: src_config)
    monkeypatch.setattr("app.backup.get_state_dir", lambda: src_state)

    archive = tmp_path / "backup.tar.gz"
    create_backup(archive)

    dest_config = tmp_path / "dest" / "config"
    monkeypatch.setattr("app.backup.get_config_dir", lambda: dest_config)
    monkeypatch.setattr("app.backup.get_state_dir", lambda: tmp_path / "dest" / "state")

    files = restore_backup(archive, dry_run=True)
    assert len(files) >= 1
    assert not dest_config.exists()  # Nothing written


def test_list_backup_contents(tmp_path: Path, monkeypatch) -> None:
    src_config = tmp_path / "src" / "config"
    src_state = tmp_path / "src" / "state"
    (src_config).mkdir(parents=True)
    (src_config / "config.json").write_text("{}", encoding="utf-8")
    (src_state).mkdir(parents=True)

    monkeypatch.setattr("app.backup.get_config_dir", lambda: src_config)
    monkeypatch.setattr("app.backup.get_state_dir", lambda: src_state)

    archive = tmp_path / "backup.tar.gz"
    create_backup(archive)

    manifest = list_backup_contents(archive)
    assert manifest["version"] == "1.0"
    assert "config/config.json" in manifest["contents"]


def test_backup_skips_lock_files(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    state_dir = tmp_path / "state"
    (config_dir).mkdir(parents=True)
    (config_dir / "config.json").write_text("{}", encoding="utf-8")
    (state_dir).mkdir(parents=True)
    (state_dir / "runtime.lock").write_text("locked", encoding="utf-8")
    (state_dir / "runtime.pid").write_text("12345", encoding="utf-8")
    (state_dir / "tasks.db").write_text("db", encoding="utf-8")

    monkeypatch.setattr("app.backup.get_config_dir", lambda: config_dir)
    monkeypatch.setattr("app.backup.get_state_dir", lambda: state_dir)

    archive = tmp_path / "backup.tar.gz"
    create_backup(archive)

    manifest = list_backup_contents(archive)
    contents = manifest["contents"]
    assert "state/tasks.db" in contents
    assert "state/runtime.lock" not in contents
    assert "state/runtime.pid" not in contents
