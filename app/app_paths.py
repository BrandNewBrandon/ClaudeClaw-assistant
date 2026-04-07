from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "assistant"
CONFIG_FILENAME = "config.json"
APP_ROOT_ENV = "ASSISTANT_APP_ROOT"


def _user_home() -> Path:
    return Path.home()


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _get_app_root_override() -> Path | None:
    override = os.environ.get(APP_ROOT_ENV)
    return Path(override) if override else None


def get_config_dir() -> Path:
    override = _get_app_root_override()
    if override is not None:
        return override / "config"
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_NAME
    if os.name == "nt":
        return _user_home() / "AppData" / "Roaming" / APP_NAME
    if _is_macos():
        return _user_home() / "Library" / "Application Support" / APP_NAME / "config"
    if os.environ.get("XDG_CONFIG_HOME"):
        return Path(os.environ["XDG_CONFIG_HOME"]) / APP_NAME
    return _user_home() / ".config" / APP_NAME


def get_data_dir() -> Path:
    override = _get_app_root_override()
    if override is not None:
        return override / "data"
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        return Path(localappdata) / APP_NAME / "data"
    if os.name == "nt":
        return _user_home() / "AppData" / "Local" / APP_NAME / "data"
    if _is_macos():
        return _user_home() / "Library" / "Application Support" / APP_NAME / "data"
    if os.environ.get("XDG_DATA_HOME"):
        return Path(os.environ["XDG_DATA_HOME"]) / APP_NAME
    return _user_home() / ".local" / "share" / APP_NAME


def get_state_dir() -> Path:
    override = _get_app_root_override()
    if override is not None:
        return override / "state"
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        return Path(localappdata) / APP_NAME / "state"
    if os.name == "nt":
        return _user_home() / "AppData" / "Local" / APP_NAME / "state"
    if _is_macos():
        return _user_home() / "Library" / "Application Support" / APP_NAME / "state"
    if os.environ.get("XDG_STATE_HOME"):
        return Path(os.environ["XDG_STATE_HOME"]) / APP_NAME
    return _user_home() / ".local" / "state" / APP_NAME


def get_logs_dir() -> Path:
    override = _get_app_root_override()
    if override is not None:
        return override / "logs"
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        return Path(localappdata) / APP_NAME / "logs"
    if os.name == "nt":
        return _user_home() / "AppData" / "Local" / APP_NAME / "logs"
    if _is_macos():
        return _user_home() / "Library" / "Logs" / APP_NAME
    return get_state_dir() / "logs"


def get_config_file() -> Path:
    return get_config_dir() / CONFIG_FILENAME


def get_agents_dir() -> Path:
    return get_config_dir() / "agents"


def get_logs_file() -> Path:
    return get_logs_dir() / "runtime.log"


def get_runtime_lock_file() -> Path:
    return get_state_dir() / "runtime.lock"


def get_runtime_pid_file() -> Path:
    return get_state_dir() / "runtime.pid"


def get_sessions_state_file() -> Path:
    return get_state_dir() / "sessions.json"


def ensure_config_dirs() -> None:
    get_config_dir().mkdir(parents=True, exist_ok=True)
    get_agents_dir().mkdir(parents=True, exist_ok=True)


def ensure_runtime_dirs() -> None:
    get_state_dir().mkdir(parents=True, exist_ok=True)
    get_logs_dir().mkdir(parents=True, exist_ok=True)
