from __future__ import annotations

from pathlib import Path, PureWindowsPath

from app import app_paths


def test_get_config_file_uses_windows_appdata(monkeypatch) -> None:
    monkeypatch.setattr(app_paths, "_is_macos", lambda: False)
    monkeypatch.setattr(app_paths.os, "name", "nt")
    monkeypatch.setenv("APPDATA", r"C:\Users\tester\AppData\Roaming")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    original_path = app_paths.Path
    monkeypatch.setattr(app_paths, "Path", PureWindowsPath)
    try:
        assert app_paths.get_config_dir() == PureWindowsPath(r"C:\Users\tester\AppData\Roaming") / "assistant"
        assert app_paths.get_config_file() == PureWindowsPath(r"C:\Users\tester\AppData\Roaming") / "assistant" / "config.json"
    finally:
        monkeypatch.setattr(app_paths, "Path", original_path)




def test_getters_do_not_create_directories(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_paths, "_is_macos", lambda: False)
    monkeypatch.setattr(app_paths.os, "name", "posix")
    monkeypatch.setattr(app_paths.Path, "home", staticmethod(lambda: tmp_path / "home"))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    config_dir = app_paths.get_config_dir()

    assert not config_dir.exists()


def test_ensure_config_dirs_creates_directories(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_paths, "_is_macos", lambda: False)
    monkeypatch.setattr(app_paths.os, "name", "posix")
    monkeypatch.setattr(app_paths.Path, "home", staticmethod(lambda: tmp_path / "home"))
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    app_paths.ensure_config_dirs()

    assert app_paths.get_config_dir().is_dir()
    assert app_paths.get_agents_dir().is_dir()


def test_app_root_override_redirects_all_categories(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(app_paths.APP_ROOT_ENV, str(tmp_path / "app-root"))

    assert app_paths.get_config_dir() == tmp_path / "app-root" / "config"
    assert app_paths.get_data_dir() == tmp_path / "app-root" / "data"
    assert app_paths.get_state_dir() == tmp_path / "app-root" / "state"
    assert app_paths.get_logs_dir() == tmp_path / "app-root" / "logs"
