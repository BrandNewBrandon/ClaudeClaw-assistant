"""Platform-specific daemon autostart registration.

Provides three public functions:
  install_autostart(project_root, python_executable) -> str
  uninstall_autostart() -> str
  autostart_status() -> str

macOS  : launchd plist at ~/Library/LaunchAgents/com.assistant.runtime.plist
Linux  : systemd user service at ~/.config/systemd/user/assistant-runtime.service
Windows: scheduled task (ONLOGON trigger) via schtasks.exe
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


_LABEL = "com.assistant.runtime"
_TASK_NAME = "AssistantRuntime"


# ---------------------------------------------------------------------------
# macOS — launchd
# ---------------------------------------------------------------------------

def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_LABEL}.plist"


def _launchd_plist_xml(python_exe: str, project_root: Path, log_path: Path) -> str:
    # Autostart target is the watchdog, not app.main directly. The watchdog
    # calls _start_runtime when the runtime pid is missing or dead, so a
    # single launchd agent keeps the runtime alive across crashes, manual
    # stops, and reboots. launchd's own KeepAlive also re-runs the watchdog
    # itself if it ever exits.
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_exe}</string>
        <string>-m</string>
        <string>app.assistant_cli</string>
        <string>watchdog</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{project_root}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>{os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")}</string>
    </dict>
</dict>
</plist>
"""


def _launchd_install(project_root: Path, python_exe: str, log_path: Path) -> str:
    plist_path = _launchd_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(_launchd_plist_xml(python_exe, project_root, log_path), encoding="utf-8")
    # Unload first (ignore errors if not loaded)
    subprocess.run(["launchctl", "unload", "-w", str(plist_path)],
                   capture_output=True, check=False)
    result = subprocess.run(["launchctl", "load", "-w", str(plist_path)],
                            capture_output=True, text=True, check=False)
    if result.returncode != 0:
        err = result.stderr.strip()
        return (
            f"Plist written to {plist_path}\n"
            f"  Warning: launchctl load returned an error: {err}\n"
            f"  The service should still start on next login."
        )
    return f"Autostart enabled via launchd.\n  Plist: {plist_path}"


def _launchd_uninstall() -> str:
    plist_path = _launchd_plist_path()
    if not plist_path.exists():
        return "No launchd plist found — autostart was not installed."
    subprocess.run(["launchctl", "unload", "-w", str(plist_path)],
                   capture_output=True, check=False)
    plist_path.unlink(missing_ok=True)
    return f"Autostart removed (deleted {plist_path})."


def _launchd_status() -> str:
    plist_path = _launchd_plist_path()
    if not plist_path.exists():
        return "Autostart: not installed (no launchd plist)."
    result = subprocess.run(
        ["launchctl", "list", _LABEL],
        capture_output=True, text=True, check=False,
    )
    if result.returncode == 0:
        return f"Autostart: installed and registered with launchd.\n  Plist: {plist_path}"
    return f"Autostart: plist exists but not loaded by launchd.\n  Plist: {plist_path}"


# ---------------------------------------------------------------------------
# Linux — systemd user service
# ---------------------------------------------------------------------------

def _systemd_service_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(config_home) / "systemd" / "user" / "assistant-runtime.service"


def _systemd_unit(python_exe: str, project_root: Path) -> str:
    # ExecStart is the watchdog; it handles runtime lifecycle and
    # restart-on-crash. systemd's Restart=on-failure is an outer safety net
    # in case the watchdog itself dies.
    return f"""\
[Unit]
Description=Assistant Runtime (via watchdog supervisor)
After=network.target

[Service]
Type=simple
ExecStart={python_exe} -m app.assistant_cli watchdog
WorkingDirectory={project_root}
Restart=on-failure
RestartSec=5
Environment=PATH={os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")}

[Install]
WantedBy=default.target
"""


def _systemd_install(project_root: Path, python_exe: str) -> str:
    unit_path = _systemd_service_path()
    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(_systemd_unit(python_exe, project_root), encoding="utf-8")

    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, check=False)
    result = subprocess.run(
        ["systemctl", "--user", "enable", "--now", "assistant-runtime"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        err = result.stderr.strip()
        return (
            f"Unit file written to {unit_path}\n"
            f"  Warning: systemctl enable returned an error: {err}\n"
            f"  Run 'systemctl --user enable --now assistant-runtime' manually."
        )
    return f"Autostart enabled via systemd.\n  Unit: {unit_path}"


def _systemd_uninstall() -> str:
    unit_path = _systemd_service_path()
    if not unit_path.exists():
        return "No systemd unit found — autostart was not installed."
    subprocess.run(["systemctl", "--user", "disable", "--now", "assistant-runtime"],
                   capture_output=True, check=False)
    unit_path.unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, check=False)
    return f"Autostart removed (deleted {unit_path})."


def _systemd_status() -> str:
    unit_path = _systemd_service_path()
    if not unit_path.exists():
        return "Autostart: not installed (no systemd unit file)."
    result = subprocess.run(
        ["systemctl", "--user", "is-enabled", "assistant-runtime"],
        capture_output=True, text=True, check=False,
    )
    enabled = result.stdout.strip()
    if enabled == "enabled":
        return f"Autostart: installed and enabled via systemd.\n  Unit: {unit_path}"
    return f"Autostart: unit file exists but is '{enabled}'.\n  Unit: {unit_path}"


# ---------------------------------------------------------------------------
# Windows — scheduled task (ONLOGON, no admin required)
# ---------------------------------------------------------------------------

def _windows_install(project_root: Path, python_exe: str) -> str:
    # Remove existing task first (ignore failure)
    subprocess.run(
        ["schtasks", "/Delete", "/TN", _TASK_NAME, "/F"],
        capture_output=True, check=False,
    )
    # Prefer pythonw.exe so the watchdog runs without a visible console
    # window. Falls back to python.exe if pythonw isn't next to python.
    exe = python_exe
    pyw = Path(python_exe).with_name("pythonw.exe")
    if pyw.exists():
        exe = str(pyw)
    action = f'"{exe}" -m app.assistant_cli watchdog'
    result = subprocess.run(
        [
            "schtasks", "/Create",
            "/TN", _TASK_NAME,
            "/TR", action,
            "/SC", "ONLOGON",
            "/RL", "LIMITED",
            "/F",
        ],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip()
        return f"Warning: schtasks create returned an error: {err}"
    return (
        f"Autostart enabled via Windows Scheduled Task '{_TASK_NAME}' (trigger: ONLOGON).\n"
        f"  Command: {action}\n"
        f"  The watchdog launches and keeps the runtime alive across crashes."
    )


def _windows_uninstall() -> str:
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", _TASK_NAME, "/F"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return f"No scheduled task '{_TASK_NAME}' found — autostart was not installed."
    return f"Autostart removed (deleted scheduled task '{_TASK_NAME}')."


def _windows_status() -> str:
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", _TASK_NAME, "/FO", "LIST"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return f"Autostart: not installed (no scheduled task '{_TASK_NAME}')."
    status_line = next(
        (line for line in result.stdout.splitlines() if "Status" in line),
        "",
    )
    return f"Autostart: scheduled task '{_TASK_NAME}' found. {status_line}".strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def install_autostart(project_root: Path, python_executable: str | None = None) -> str:
    """Register the runtime as a login-time autostart service.

    Returns a human-readable description of what was done.
    """
    from .app_paths import get_logs_file  # avoid circular at module level

    exe = python_executable or sys.executable
    log = get_logs_file()

    if sys.platform == "darwin":
        return _launchd_install(project_root, exe, log)
    if os.name == "nt":
        return _windows_install(project_root, exe)
    # Linux / everything else → systemd user session
    return _systemd_install(project_root, exe)


def uninstall_autostart() -> str:
    """Remove the autostart registration.

    Returns a human-readable description of what was done.
    """
    if sys.platform == "darwin":
        return _launchd_uninstall()
    if os.name == "nt":
        return _windows_uninstall()
    return _systemd_uninstall()


def autostart_status() -> str:
    """Return human-readable status of the autostart registration."""
    if sys.platform == "darwin":
        return _launchd_status()
    if os.name == "nt":
        return _windows_status()
    return _systemd_status()
