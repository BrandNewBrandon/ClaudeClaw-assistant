from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .app_paths import get_config_file, get_logs_file, get_runtime_lock_file, get_runtime_pid_file, get_sessions_state_file
from .config import ConfigError, load_config


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    message: str


def run_doctor(config_path: str | Path) -> list[DoctorCheck]:
    path = Path(config_path)
    checks: list[DoctorCheck] = []

    expected_config_path = get_config_file()
    if not path.exists():
        checks.append(DoctorCheck("config", "fail", f"Config file missing: {path}"))
        checks.append(DoctorCheck("config-path", "ok", f"Canonical config path: {expected_config_path}"))
        return checks

    checks.append(DoctorCheck("config", "ok", f"Config file exists: {path}"))
    checks.append(DoctorCheck("config-path", "ok", f"Canonical config path: {expected_config_path}"))

    try:
        config = load_config(path)
    except ConfigError as exc:
        checks.append(DoctorCheck("config-load", "fail", str(exc)))
        return checks

    checks.append(DoctorCheck("provider", "ok", f"Model provider: {config.model_provider}"))
    checks.append(DoctorCheck("project-root", "ok", f"Project root: {config.project_root}"))
    checks.append(DoctorCheck("agents-path", "ok", f"Agents path: {config.agents_dir}"))
    checks.append(DoctorCheck("shared-path", "ok", f"Shared path: {config.shared_dir}"))
    checks.append(DoctorCheck("runtime-pid", "ok", f"Runtime PID path: {get_runtime_pid_file()}"))
    checks.append(DoctorCheck("runtime-lock", "ok", f"Runtime lock path: {get_runtime_lock_file()}"))
    checks.append(DoctorCheck("runtime-log", "ok", f"Runtime log path: {get_logs_file()}"))
    checks.append(DoctorCheck("session-state", "ok", f"Session state path: {get_sessions_state_file()}"))

    if shutil.which("claude") is None:
        checks.append(DoctorCheck("claude", "warn", "`claude` CLI not found in PATH."))
    else:
        checks.append(DoctorCheck("claude", "ok", "`claude` CLI found in PATH."))

    default_agent_dir = config.agents_dir / config.default_agent
    if default_agent_dir.exists():
        checks.append(DoctorCheck("default-agent", "ok", f"Default agent exists: {config.default_agent}"))
    else:
        checks.append(DoctorCheck("default-agent", "fail", f"Default agent missing: {config.default_agent}"))

    if config.agents_dir.exists():
        checks.append(DoctorCheck("agents-dir", "ok", f"Agents directory exists: {config.agents_dir}"))
    else:
        checks.append(DoctorCheck("agents-dir", "fail", f"Agents directory missing: {config.agents_dir}"))

    if config.shared_dir.exists():
        checks.append(DoctorCheck("shared-dir", "ok", f"Shared directory exists: {config.shared_dir}"))
    else:
        checks.append(DoctorCheck("shared-dir", "warn", f"Shared directory missing: {config.shared_dir}"))

    seen_tokens: dict[str, str] = {}
    for account_id, account in sorted(config.accounts.items()):
        checks.append(
            DoctorCheck(
                "account",
                "ok",
                f"Account {account_id}: platform={account.platform} allowed_chat_ids={len(account.allowed_chat_ids)}",
            )
        )
        if not account.allowed_chat_ids:
            checks.append(DoctorCheck("allowed-chat-ids", "fail", f"Account {account_id} has no allowed chat IDs configured."))

        prior = seen_tokens.get(account.token)
        if prior is not None:
            checks.append(DoctorCheck("account-token", "warn", f"Accounts {prior} and {account_id} share the same Telegram token."))
        else:
            seen_tokens[account.token] = account_id

        routing = config.routing.get(account_id)
        if routing is None:
            checks.append(DoctorCheck("routing", "fail", f"Account {account_id} is missing routing config."))
            continue

        default_agent_dir = config.agents_dir / routing.default_agent
        if default_agent_dir.exists():
            checks.append(DoctorCheck("default-agent", "ok", f"Account {account_id} default agent exists: {routing.default_agent}"))
        else:
            checks.append(DoctorCheck("default-agent", "fail", f"Account {account_id} default agent missing: {routing.default_agent}"))

        for chat_id, agent_name in sorted(routing.chat_agent_map.items()):
            agent_dir = config.agents_dir / agent_name
            if agent_dir.exists():
                checks.append(DoctorCheck("routing", "ok", f"Account {account_id} chat {chat_id} routes to {agent_name}"))
            else:
                checks.append(DoctorCheck("routing", "warn", f"Account {account_id} chat {chat_id} routes to missing agent: {agent_name}"))

    # ── Platform-specific checks ─────────────────────────────────────────────
    platforms_used = {a.platform for a in config.accounts.values()}

    if "imessage" in platforms_used:
        import platform as _platform
        if _platform.system() != "Darwin":
            checks.append(DoctorCheck("imessage", "fail", "iMessage requires macOS, but this system is not macOS."))
        else:
            db_path = Path.home() / "Library" / "Messages" / "chat.db"
            if db_path.exists():
                checks.append(DoctorCheck("imessage-db", "ok", f"Messages database found: {db_path}"))
            else:
                checks.append(DoctorCheck("imessage-db", "fail",
                    f"Messages database not found at {db_path}. "
                    "Ensure Messages app is configured and Full Disk Access is granted to Terminal."))

    if "whatsapp" in platforms_used:
        for account_id, account in config.accounts.items():
            if account.platform != "whatsapp":
                continue
            bridge_url = (account.channel_config or {}).get("bridge_url", "http://localhost:3000")
            try:
                import urllib.request
                req = urllib.request.Request(f"{bridge_url}/messages?since=2000-01-01T00:00:00Z", method="GET")
                if account.token:
                    req.add_header("Authorization", f"Bearer {account.token}")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    resp.read()
                checks.append(DoctorCheck("whatsapp-bridge", "ok", f"WhatsApp bridge reachable at {bridge_url}"))
            except Exception as exc:
                checks.append(DoctorCheck("whatsapp-bridge", "warn",
                    f"WhatsApp bridge not reachable at {bridge_url}: {exc}. "
                    "Ensure your bridge server is running."))

    # ── Optional dependency checks ───────────────────────────────────────────
    # Check for pymupdf (PDF support)
    try:
        import fitz  # pymupdf
        checks.append(DoctorCheck("pymupdf", "ok", "pymupdf installed — PDF document support available."))
    except ImportError:
        checks.append(DoctorCheck("pymupdf", "warn", "pymupdf not installed — PDF documents will not be processed. Install with: pip install pymupdf"))

    # Check for pyautogui (computer use)
    try:
        import pyautogui  # noqa: F401
        checks.append(DoctorCheck("pyautogui", "ok", "pyautogui installed — computer use tools available."))
    except ImportError:
        # Only warn if any agent has computer_use enabled
        from .agent_config import load_agent_config
        any_cu = False
        if config.agents_dir.exists():
            for agent_path in config.agents_dir.iterdir():
                if agent_path.is_dir():
                    try:
                        ac = load_agent_config(agent_path)
                        if ac.computer_use:
                            any_cu = True
                            break
                    except Exception:
                        pass
        if any_cu:
            checks.append(DoctorCheck("pyautogui", "warn",
                "pyautogui not installed but computer_use is enabled for an agent. "
                "Install with: pip install pyautogui Pillow"))
        else:
            checks.append(DoctorCheck("pyautogui", "ok", "pyautogui not installed (not needed — no agent has computer_use enabled)."))

    # Check for semantic search dependencies
    try:
        import fastembed  # noqa: F401
        import numpy  # noqa: F401
        checks.append(DoctorCheck("semantic", "ok", "fastembed + numpy installed — semantic memory search available."))
    except ImportError:
        if config.semantic_search_enabled:
            checks.append(DoctorCheck("semantic", "warn",
                "Semantic search is enabled but fastembed/numpy not installed. "
                "Falling back to keyword search. Install with: pip install fastembed numpy"))
        else:
            checks.append(DoctorCheck("semantic", "ok", "Semantic search disabled (fastembed not needed)."))

    return checks
