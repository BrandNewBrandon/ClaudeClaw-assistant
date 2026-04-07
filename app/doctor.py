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

    return checks
