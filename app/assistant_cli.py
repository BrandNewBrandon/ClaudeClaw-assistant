from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from .app_paths import ensure_runtime_dirs, get_config_file, get_logs_file, get_runtime_lock_file, get_runtime_pid_file
from .config_manager import ensure_config_exists, load_raw_config, update_config_values, write_config
from .doctor import run_doctor


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="assistant command surface")
    subparsers = parser.add_subparsers(dest="command", required=True)

    chat_parser = subparsers.add_parser("chat", help="Chat with an agent in the terminal")
    chat_parser.add_argument("--agent", default=None, help="Agent name (default: from config)")
    chat_parser.add_argument("--chat-id", default="terminal", dest="chat_id", help="Session ID for transcript continuity (default: terminal)")

    subparsers.add_parser("init", help="First-time setup wizard")
    subparsers.add_parser("configure", help="Reconfigure the runtime (re-runs setup prompts)")

    doctor_parser = subparsers.add_parser("doctor", help="Check runtime setup and health")
    doctor_parser.add_argument("--fix", action="store_true", help="Attempt to auto-fix common issues")

    subparsers.add_parser("start", help="Start the runtime")
    subparsers.add_parser("status", help="Show runtime status")
    subparsers.add_parser("stop", help="Stop the runtime")
    subparsers.add_parser("test", help="Show test command guidance")

    manage_parser = subparsers.add_parser("manage", help="Run agent management commands")
    manage_parser.add_argument("manage_args", nargs=argparse.REMAINDER)

    # ── Short agent commands ─────────────────────────────────────────────────
    p_add = subparsers.add_parser("add", help="Create a new agent (interactive wizard)")
    p_add.add_argument("name", help="Agent name (lowercase letters, numbers, and dashes)")

    subparsers.add_parser("list-agents", help="List all agents")

    p_show = subparsers.add_parser("show", help="Show agent details")
    p_show.add_argument("name", help="Agent name")

    p_clone = subparsers.add_parser("clone", help="Copy an existing agent")
    p_clone.add_argument("source", help="Agent to copy from")
    p_clone.add_argument("target", help="Name for the new copy")

    p_rename = subparsers.add_parser("rename", help="Rename an agent")
    p_rename.add_argument("source", help="Current agent name")
    p_rename.add_argument("target", help="New agent name")

    p_delete = subparsers.add_parser("delete", help="Archive (delete) an agent")
    p_delete.add_argument("name", help="Agent name")
    p_delete.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    p_restore = subparsers.add_parser("restore", help="Restore an archived agent")
    p_restore.add_argument("name", help="Archived agent name")
    p_restore.add_argument("--as", dest="restored_name", default=None, help="Restore under a different name")

    subparsers.add_parser("restart", help="Stop and restart the runtime")
    subparsers.add_parser("update", help="Pull latest code from GitHub and update dependencies")

    logs_parser = subparsers.add_parser("logs", help="Tail the runtime log")
    logs_parser.add_argument("-n", "--lines", type=int, default=50, help="Lines of history to show (default: 50)")
    logs_parser.add_argument("--no-follow", action="store_true", help="Print last N lines and exit (don't tail)")

    ui_parser = subparsers.add_parser("ui", help="Start the web dashboard at localhost:18789")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    ui_parser.add_argument("--port", type=int, default=18789, help="Bind port (default: 18789)")

    subparsers.add_parser("mcp", help="Start the MCP stdio server")

    uninstall_parser = subparsers.add_parser("uninstall", help="Remove all runtime data and config")
    uninstall_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts")

    daemon_parser = subparsers.add_parser("daemon", help="Manage daemon autostart registration")
    daemon_sub = daemon_parser.add_subparsers(dest="daemon_action", required=True)
    daemon_sub.add_parser("install", help="Register autostart on login (launchd / systemd / schtasks)")
    daemon_sub.add_parser("uninstall", help="Remove autostart registration")
    daemon_sub.add_parser("status", help="Show autostart registration status")

    return parser


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _print_quick_help() -> None:
    print("assistant command surface")
    print("")
    print("First time? Run:  assistant init")
    print("")
    print("Commands:")
    print("  assistant init              First-time setup wizard")
    print("  assistant configure         Reconfigure settings")
    print("  assistant doctor [--fix]    Health check (--fix auto-repairs)")
    print("  assistant start / stop      Manage the runtime daemon")
    print("  assistant status            Show daemon status")
    print("  assistant daemon install    Enable autostart on login")
    print("  assistant daemon uninstall  Remove autostart")
    print("  assistant daemon status     Show autostart registration")
    print("  assistant chat              Chat with an agent in the terminal")
    print("  assistant chat --agent <n>  Chat with a specific agent")
    print("  assistant ui                Open web dashboard (localhost:18789)")
    print("  assistant mcp               Start MCP stdio server")
    print("  assistant add <name>        Create a new agent (interactive wizard)")
    print("  assistant list-agents       List all agents")
    print("  assistant show <name>       Show agent details")
    print("  assistant clone <src> <dst> Copy an agent")
    print("  assistant rename <src> <dst> Rename an agent")
    print("  assistant delete <name>     Archive an agent")
    print("  assistant manage <cmd>      Agent management (extended commands)")
    print("  assistant test              Show test command guidance")
    print("  assistant uninstall         Remove all runtime data and config")


def _mask_secret(value: str | None) -> str | None:
    if not value:
        return value
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _prompt(current: str | None, label: str, *, secret: bool = False) -> str | None:
    display_value = _mask_secret(current) if secret else current
    suffix = f" [{display_value}]" if display_value else ""
    value = input(f"{label}{suffix}: ").strip()
    return current if not value else value


def _prompt_required(label: str, *, secret: bool = False, default: str | None = None) -> str:
    """Prompt until a non-empty value is entered."""
    while True:
        value = _prompt(default, label, secret=secret)
        if value and value.strip():
            return value.strip()
        print("  (required — please enter a value)")


def _hr(char: str = "─", width: int = 60) -> None:
    print(char * width)


def _section(title: str) -> None:
    print()
    _hr()
    print(f"  {title}")
    _hr()


def _info(text: str) -> None:
    for line in text.strip().splitlines():
        print(f"  {line}")


# ---------------------------------------------------------------------------
# Agent scaffolding
# ---------------------------------------------------------------------------

_DEFAULT_AGENT_MD = """\
# AGENT.md

## Identity

You are a personal assistant for this runtime.

## Vibe

Direct, resourceful, and useful. No filler. Be grounded.

## Core rules

- Be genuinely useful.
- Prefer concrete action over vague encouragement.
- Respect privacy.
- Ask before destructive or external actions.
- Use the workspace files as continuity.
- Avoid pretending to remember things that are not written down.

## Role

Primary personal assistant for the human.
"""

_DEFAULT_USER_MD = """\
# USER.md

Fill in details about the user here so the agent can better serve them.

Examples:
- Name/preferred name
- Timezone / location
- Areas of work or interest
- How they prefer to communicate
"""

_DEFAULT_MEMORY_MD = """\
# MEMORY.md

Long-term memory for this agent. Key facts, preferences, and context accumulate here over time.
"""

_DEFAULT_TOOLS_MD = """\
# TOOLS.md

Notes about tools or local integrations available to this agent.
"""


def _scaffold_agent(agents_dir: Path, agent_name: str) -> None:
    """Create a minimal agent directory structure."""
    agent_dir = agents_dir / agent_name
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "memory").mkdir(exist_ok=True)
    (agent_dir / "sessions").mkdir(exist_ok=True)

    files = {
        "AGENT.md": _DEFAULT_AGENT_MD,
        "USER.md": _DEFAULT_USER_MD,
        "MEMORY.md": _DEFAULT_MEMORY_MD,
        "TOOLS.md": _DEFAULT_TOOLS_MD,
    }
    for filename, content in files.items():
        path = agent_dir / filename
        if not path.exists():
            path.write_text(content.strip() + "\n", encoding="utf-8")

    print(f"  Scaffolded agent: {agents_dir / agent_name}")


# ---------------------------------------------------------------------------
# Platform-specific setup instructions
# ---------------------------------------------------------------------------

_PLATFORM_INSTRUCTIONS: dict[str, str] = {
    "telegram": """\
How to get your Telegram bot token:
  1. Open Telegram and search for @BotFather
  2. Send /newbot and follow the prompts
  3. Copy the token it gives you (looks like 123456789:ABCdef...)

How to get your chat ID:
  1. Start a conversation with your new bot (send it any message)
  2. Visit: https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
  3. Look for "chat":{"id": <number>} — that number is your chat ID
""",
    "discord": """\
How to get your Discord bot token:
  1. Go to https://discord.com/developers/applications
  2. Click "New Application", give it a name
  3. Go to "Bot" in the left sidebar → "Add Bot"
  4. Under "Token", click "Reset Token" and copy it
  5. Under "Privileged Gateway Intents", enable "Message Content Intent"
  6. Invite the bot to your server via OAuth2 → URL Generator
     (scopes: bot; permissions: Send Messages, Read Message History)

How to get your channel/server ID (chat ID):
  1. Enable Developer Mode in Discord: Settings → Advanced → Developer Mode
  2. Right-click the channel you want → "Copy Channel ID"
     (or right-click your server → "Copy Server ID")
""",
    "slack": """\
How to create a Slack app and get tokens:
  1. Go to https://api.slack.com/apps → "Create New App" → "From scratch"
  2. Under "Socket Mode", enable it — you'll get an App-Level Token (xapp-...)
  3. Under "OAuth & Permissions", add Bot Token Scopes:
       chat:write, channels:history, groups:history, im:history, mpim:history
  4. Install the app to your workspace → copy the Bot User OAuth Token (xoxb-...)
  5. Invite the bot to a channel: /invite @YourBotName

Config values:
  token       = Bot User OAuth Token  (xoxb-...)
  app_token   = App-Level Token       (xapp-...)
  chat ID     = Channel ID (enable Developer Mode in Slack, right-click channel)
""",
}


# ---------------------------------------------------------------------------
# Init wizard
# ---------------------------------------------------------------------------

def _run_init(project_root: Path) -> int:
    config_path = get_config_file()
    example_path = project_root / "config" / "config.example.json"

    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║        assistant-runtime  ·  First-time setup    ║")
    print("╚══════════════════════════════════════════════════╝")
    print()

    if config_path.exists():
        print(f"Config already exists at: {config_path}")
        answer = input("Re-run setup anyway? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            print("Skipped. Run 'assistant configure' to change individual settings.")
            return 0

    # ── Step 1: Check prerequisites ─────────────────────────────────────────
    _section("Step 1 of 5 — Prerequisites")
    _info("Checking required tools...")

    issues: list[str] = []
    if shutil.which("claude") is None:
        issues.append("'claude' CLI not found in PATH")
        _info("  [MISSING] claude CLI — install from: https://claude.ai/code")
    else:
        _info("  [OK] claude CLI found")

    if issues:
        print()
        print("  Some prerequisites are missing. You can continue setup")
        print("  and install them before running 'assistant start'.")
        input("  Press Enter to continue...")

    # ── Step 2: Platform ─────────────────────────────────────────────────────
    _section("Step 2 of 5 — Messaging Platform")
    _info("Which messaging platform do you want to use?")
    _info("")
    _info("  1) Telegram  (recommended, easiest to set up)")
    _info("  2) Discord")
    _info("  3) Slack")
    print()

    platform_map = {"1": "telegram", "2": "discord", "3": "slack"}
    while True:
        choice = input("  Enter 1, 2, or 3 [1]: ").strip() or "1"
        if choice in platform_map:
            platform = platform_map[choice]
            break
        print("  Please enter 1, 2, or 3.")

    # ── Step 3: Token + chat ID ───────────────────────────────────────────────
    _section(f"Step 3 of 5 — {platform.capitalize()} Token & Chat ID")
    print()
    _info(_PLATFORM_INSTRUCTIONS[platform])

    token = _prompt_required(f"  {platform.capitalize()} bot token", secret=True)
    print()

    chat_ids_raw = _prompt_required("  Allowed chat IDs (comma-separated)")
    chat_ids = [c.strip() for c in chat_ids_raw.split(",") if c.strip()]

    channel_config: dict[str, str] = {}
    if platform == "slack":
        print()
        app_token = _prompt_required("  Slack App-Level Token (xapp-...)", secret=True)
        channel_config["app_token"] = app_token

    # ── Step 4: Agent ─────────────────────────────────────────────────────────
    _section("Step 4 of 5 — Default Agent")
    _info("An 'agent' is the AI persona your assistant uses.")
    _info("You can have multiple agents for different purposes.")
    _info("")
    _info("Common names: main, assistant, jarvis, friday, personal")
    print()

    agent_name = input("  Default agent name [main]: ").strip() or "main"
    agents_dir = project_root / "agents"
    shared_dir = project_root / "shared"

    print()
    _scaffold_agent(agents_dir, agent_name)

    # ── Step 5: Write config ───────────────────────────────────────────────────
    _section("Step 5 of 5 — Saving Config")

    ensure_config_exists(config_path, example_path)
    base = load_raw_config(config_path)

    # Build the account entry
    account_entry: dict = {
        "platform": platform,
        "token": token,
        "allowed_chat_ids": chat_ids,
    }
    if channel_config:
        account_entry["channel_config"] = channel_config

    updates: dict = {
        "project_root": str(project_root),
        "agents_dir": str(agents_dir),
        "shared_dir": str(shared_dir),
        "default_agent": agent_name,
        "model_provider": "claude-code",
        "accounts": {"primary": account_entry},
        "routing": {"primary": {"default_agent": agent_name, "chat_agent_map": {}}},
    }
    base.update(updates)
    write_config(config_path, base)
    print(f"  Config written to: {config_path}")

    # ── Step 6: Autostart ─────────────────────────────────────────────────────
    _section("Step 6 of 6 — Autostart (optional)")
    import sys as _sys
    if _sys.platform == "darwin":
        _info("macOS: registers a launchd agent that starts the runtime when you log in")
        _info("       and automatically restarts it if it ever crashes.")
    elif os.name == "nt":
        _info("Windows: creates an ONLOGON scheduled task so the runtime starts at login.")
    else:
        _info("Linux: creates a systemd user service that starts on login and")
        _info("       restarts automatically on crash.")
    print()

    autostart_answer = input("  Enable autostart? [Y/n]: ").strip().lower()
    autostart_enabled = autostart_answer in ("", "y", "yes")
    if autostart_enabled:
        from .daemon_service import install_autostart
        msg = install_autostart(project_root)
        _info(msg)
        print()
        _info("Starting the runtime now...")
        _start_runtime(project_root)
    else:
        _info("Skipped. Run 'assistant daemon install' at any time to enable autostart.")
        _info("Run 'assistant start' to launch the runtime manually.")
    print()

    # ── Summary ────────────────────────────────────────────────────────────────
    _section("Setup Complete")
    _info("Next steps:")
    _info("")
    _info("  1. Run 'assistant doctor' to verify everything looks good")
    _info("  2. Message your bot — it will reply!")
    _info("     (if autostart was enabled above, the runtime is already running)")
    _info("     (otherwise run 'assistant start' first)")
    _info("")
    _info(f"  Agent files: {agents_dir / agent_name}/")
    _info(f"    Edit AGENT.md  to shape the assistant's personality")
    _info(f"    Edit USER.md   to give the agent context about you")
    _info("")
    _info("  Run 'assistant ui' to open the web dashboard.")
    print()

    # Run doctor automatically
    print("Running health check...")
    print()
    checks = run_doctor(config_path)
    for check in checks:
        icon = "[OK]" if check.status == "ok" else f"[{check.status.upper()}]"
        print(f"  {icon} {check.message}")

    failed = [c for c in checks if c.status == "fail"]
    warned = [c for c in checks if c.status == "warn"]
    print()
    if failed:
        print(f"  {len(failed)} issue(s) to resolve before starting.")
    elif warned:
        print(f"  Setup complete with {len(warned)} warning(s). Run 'assistant start' when ready.")
    else:
        print("  All checks passed. Run 'assistant start' to go live!")
    print()
    return 0 if not failed else 1


# ---------------------------------------------------------------------------
# Configure (improved)
# ---------------------------------------------------------------------------

def _run_configure(project_root: Path) -> int:
    config_path = get_config_file()
    example_path = project_root / "config" / "config.example.json"

    ensure_config_exists(config_path, example_path)
    current = _seed_project_paths(load_raw_config(config_path), project_root)

    # Detect current platform from accounts if present
    accounts = current.get("accounts", {})
    primary_account = accounts.get("primary", {}) if isinstance(accounts, dict) else {}
    current_platform = primary_account.get("platform", "telegram") if isinstance(primary_account, dict) else "telegram"
    current_token = primary_account.get("token", current.get("telegram_bot_token", "")) if isinstance(primary_account, dict) else current.get("telegram_bot_token", "")
    current_chat_ids = primary_account.get("allowed_chat_ids", current.get("allowed_chat_ids", [])) if isinstance(primary_account, dict) else current.get("allowed_chat_ids", [])

    print()
    _section("Configure assistant-runtime")
    _info(f"Config file: {config_path}")
    _info("Press Enter to keep the current value shown in [brackets].")
    print()

    # Platform
    _info(f"Current platform: {current_platform}")
    _info("Platforms: telegram, discord, slack")
    platform_input = input(f"  Platform [{current_platform}]: ").strip().lower() or current_platform
    if platform_input not in ("telegram", "discord", "slack"):
        print(f"  Unknown platform '{platform_input}', keeping '{current_platform}'")
        platform_input = current_platform

    if platform_input != current_platform:
        print()
        _info(f"Setup instructions for {platform_input}:")
        _info(_PLATFORM_INSTRUCTIONS[platform_input])

    print()
    token = _prompt(current_token or None, f"  {platform_input.capitalize()} bot token", secret=True) or current_token
    print()

    chat_ids_raw = _prompt(",".join(current_chat_ids) or None, "  Allowed chat IDs (comma-separated)")
    chat_ids = [c.strip() for c in (chat_ids_raw or "").split(",") if c.strip()] or current_chat_ids

    channel_config: dict[str, str] = {}
    if platform_input == "slack":
        current_app_token = (primary_account.get("channel_config") or {}).get("app_token", "") if isinstance(primary_account, dict) else ""
        print()
        app_token = _prompt(current_app_token or None, "  Slack App-Level Token (xapp-...)", secret=True) or current_app_token
        if app_token:
            channel_config["app_token"] = app_token

    print()
    default_agent = _prompt(current.get("default_agent"), "  Default agent name") or current.get("default_agent", "main")
    claude_model = _prompt(current.get("claude_model"), "  Claude model (leave blank for default)")
    claude_effort = _prompt(current.get("claude_effort"), "  Claude effort level (leave blank for default)")
    print()

    # Build updated account
    account_entry: dict = {
        "platform": platform_input,
        "token": token,
        "allowed_chat_ids": chat_ids,
    }
    if channel_config:
        account_entry["channel_config"] = channel_config

    updates: dict = {
        "default_agent": default_agent,
        "model_provider": "claude-code",
        "accounts": {"primary": account_entry},
        "routing": {"primary": {"default_agent": default_agent, "chat_agent_map": {}}},
    }
    if claude_model:
        updates["claude_model"] = claude_model
    if claude_effort:
        updates["claude_effort"] = claude_effort

    current.update(updates)
    write_config(config_path, current)
    print(f"  Config updated: {config_path}")
    print()

    # Scaffold default agent if missing
    agents_dir = Path(current.get("agents_dir", str(project_root / "agents"))).expanduser()
    if default_agent and not (agents_dir / default_agent).exists():
        print(f"  Agent '{default_agent}' not found — scaffolding...")
        _scaffold_agent(agents_dir, default_agent)

    print("  Run 'assistant doctor' to verify the setup.")
    print("  Run 'assistant start' to launch.")
    print()
    return 0


# ---------------------------------------------------------------------------
# Doctor --fix
# ---------------------------------------------------------------------------

def _run_doctor(config_path: Path, *, fix: bool = False, project_root: Path | None = None) -> int:
    checks = run_doctor(config_path)
    fixed: list[str] = []
    failed_after_fix: list[str] = []

    for check in checks:
        icon = "[OK]  " if check.status == "ok" else f"[{check.status.upper()}]"
        print(f"  {icon} {check.message}")

        if not fix or check.status not in ("fail", "warn"):
            continue

        # Auto-fix: missing agents directory
        if check.name == "agents-dir":
            try:
                from .config_manager import load_raw_config
                cfg = load_raw_config(config_path)
                root = project_root or Path(cfg.get("project_root", ".")).expanduser()
                agents_dir = Path(cfg.get("agents_dir", str(root / "agents"))).expanduser()
                agents_dir.mkdir(parents=True, exist_ok=True)
                fixed.append(f"Created agents directory: {agents_dir}")
            except Exception as exc:
                failed_after_fix.append(f"Could not create agents dir: {exc}")

        # Auto-fix: missing default agent
        elif check.name == "default-agent":
            try:
                from .config_manager import load_raw_config
                cfg = load_raw_config(config_path)
                root = project_root or Path(cfg.get("project_root", ".")).expanduser()
                agents_dir = Path(cfg.get("agents_dir", str(root / "agents"))).expanduser()

                routing = cfg.get("routing", {})
                primary_routing = routing.get("primary", {}) if isinstance(routing, dict) else {}
                agent_name = primary_routing.get("default_agent", cfg.get("default_agent", "main")) if isinstance(primary_routing, dict) else cfg.get("default_agent", "main")

                _scaffold_agent(agents_dir, agent_name)
                fixed.append(f"Scaffolded missing agent: {agent_name}")
            except Exception as exc:
                failed_after_fix.append(f"Could not scaffold agent: {exc}")

        # Auto-fix: missing shared directory
        elif check.name == "shared-dir":
            try:
                from .config_manager import load_raw_config
                cfg = load_raw_config(config_path)
                root = project_root or Path(cfg.get("project_root", ".")).expanduser()
                shared_dir = Path(cfg.get("shared_dir", str(root / "shared"))).expanduser()
                (shared_dir / "transcripts").mkdir(parents=True, exist_ok=True)
                fixed.append(f"Created shared directory: {shared_dir}")
            except Exception as exc:
                failed_after_fix.append(f"Could not create shared dir: {exc}")

    if fix:
        print()
        if fixed:
            print("  Auto-fixed:")
            for msg in fixed:
                print(f"    + {msg}")
        if failed_after_fix:
            print("  Could not fix:")
            for msg in failed_after_fix:
                print(f"    ! {msg}")
        if not fixed and not failed_after_fix:
            print("  Nothing to fix.")
        print()
        if fixed:
            print("  Re-running checks after fixes...")
            print()
            return _run_doctor(config_path, fix=False, project_root=project_root)

    failed = [c for c in checks if c.status == "fail"]
    return 0 if not failed else 1


# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------

def _confirm(prompt: str, *, yes: bool = False) -> bool:
    if yes:
        print(f"  {prompt} [auto-confirmed]")
        return True
    answer = input(f"  {prompt} [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def _remove_tree(path: Path, label: str) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
        print(f"  Removed: {path}  ({label})")
    else:
        print(f"  Skipped (not found): {path}")


def _run_uninstall(*, yes: bool = False, project_root: Path) -> int:
    from .app_paths import get_config_dir, get_data_dir, get_state_dir, get_logs_dir

    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║        assistant-runtime  ·  Uninstall           ║")
    print("╚══════════════════════════════════════════════════╝")
    print()
    print("  This will remove runtime data, config, and logs.")
    print("  Your agent files (AGENT.md, MEMORY.md, etc.) are")
    print("  stored in the agents/ directory of the project and")
    print("  will be removed only if you confirm below.")
    print()

    if not yes:
        answer = input("  Continue with uninstall? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            print("  Aborted.")
            return 0

    # 1. Stop daemon if running
    print()
    print("  Stopping runtime daemon...")
    pid_path = get_runtime_pid_file()
    pid = _read_pid(pid_path)
    if pid and _is_process_running(pid):
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
            for _ in range(20):
                if not _is_process_running(pid):
                    break
                time.sleep(0.1)
            print(f"  Stopped daemon (PID {pid}).")
        except OSError as exc:
            print(f"  Warning: could not stop daemon: {exc}")
    else:
        print("  Daemon not running.")

    # 2. Remove state dir (PID, lock, tasks DB, sessions)
    print()
    state_dir = get_state_dir()
    if _confirm(f"Remove state directory? ({state_dir})", yes=yes):
        _remove_tree(state_dir, "state: PID, lock, tasks DB, sessions")

    # 3. Remove logs
    logs_dir = get_logs_dir()
    if _confirm(f"Remove logs? ({logs_dir})", yes=yes):
        _remove_tree(logs_dir, "logs")

    # 4. Remove config (includes config.json)
    config_dir = get_config_dir()
    if _confirm(f"Remove config directory? ({config_dir})", yes=yes):
        _remove_tree(config_dir, "config.json and related files")

    # 5. Remove data dir if it exists and is distinct
    data_dir = get_data_dir()
    if data_dir != state_dir and data_dir != config_dir and data_dir.exists():
        if _confirm(f"Remove data directory? ({data_dir})", yes=yes):
            _remove_tree(data_dir, "data")

    # 6. Remove shared dir (transcripts, etc.)
    try:
        cfg_path = get_config_file()
        if cfg_path.exists():
            cfg = load_raw_config(cfg_path)
        else:
            cfg = {}
        shared_dir = Path(cfg.get("shared_dir", str(project_root / "shared"))).expanduser()
    except Exception:
        shared_dir = project_root / "shared"

    if shared_dir.exists():
        if _confirm(f"Remove shared data directory? ({shared_dir}  — transcripts, etc.)", yes=yes):
            _remove_tree(shared_dir, "shared data")

    # 7. Optionally remove agent files
    try:
        cfg_path = get_config_file()
        if cfg_path.exists():
            cfg = load_raw_config(cfg_path)
        else:
            cfg = {}
        agents_dir = Path(cfg.get("agents_dir", str(project_root / "agents"))).expanduser()
    except Exception:
        agents_dir = project_root / "agents"

    print()
    print("  Agent files contain your AGENT.md, USER.md, MEMORY.md, and daily notes.")
    if agents_dir.exists():
        if _confirm(f"Remove agent files? ({agents_dir}  — THIS DELETES YOUR AGENT DATA)", yes=False):
            _remove_tree(agents_dir, "agent files")
        else:
            print(f"  Kept agent files at: {agents_dir}")

    # 8. Pip uninstall hint
    print()
    print("  ─────────────────────────────────────────────────")
    print("  To also remove the Python package, run:")
    print("    pip uninstall assistant-runtime")
    print("  ─────────────────────────────────────────────────")
    print()
    print("  Uninstall complete.")
    print()
    return 0


# ---------------------------------------------------------------------------
# Runtime management helpers (unchanged)
# ---------------------------------------------------------------------------

def _seed_project_paths(config: dict, project_root: Path) -> dict:
    seeded = dict(config)
    seeded.setdefault("project_root", str(project_root))
    seeded.setdefault("agents_dir", str(project_root / "agents"))
    seeded.setdefault("shared_dir", str(project_root / "shared"))
    return seeded


def _read_pid(pid_path: Path) -> int | None:
    if not pid_path.exists():
        return None
    try:
        raw = pid_path.read_text(encoding="utf-8").strip()
        return int(raw) if raw else None
    except (OSError, ValueError):
        return None


def _is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, check=False,
        )
        output = (result.stdout or "").strip()
        if result.returncode != 0 or not output:
            return False
        lowered = output.lower()
        return "no tasks are running" not in lowered and "info:" not in lowered
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        pass


def _read_lock_pid(lock_path: Path) -> int | None:
    if not lock_path.exists():
        return None
    try:
        raw = lock_path.read_text(encoding="utf-8").strip()
        return int(raw) if raw else None
    except (OSError, ValueError):
        return None


def _cleanup_stale_runtime_files() -> None:
    pid_path = get_runtime_pid_file()
    lock_path = get_runtime_lock_file()
    pid = _read_pid(pid_path)
    if pid is not None and not _is_process_running(pid):
        _safe_unlink(pid_path)
    lock_pid = _read_lock_pid(lock_path)
    if lock_pid is None:
        if lock_path.exists():
            _safe_unlink(lock_path)
        return
    if not _is_process_running(lock_pid):
        _safe_unlink(lock_path)


def _cmd_update(project_root: Path) -> int:
    venv_pip = project_root / ".venv" / "bin" / "pip"
    if os.name == "nt":
        venv_pip = project_root / ".venv" / "Scripts" / "pip.exe"

    # Check git is available and we're in a repo
    if not (project_root / ".git").exists():
        print("Error: project directory is not a git repository.")
        print(f"  Expected: {project_root}/.git")
        return 1

    print("Pulling latest code from GitHub...")
    result = subprocess.run(["git", "pull"], cwd=str(project_root))
    if result.returncode != 0:
        print("Error: git pull failed. Check your internet connection and try again.")
        return result.returncode

    print("\nUpdating dependencies...")
    pip_cmd = str(venv_pip) if venv_pip.exists() else "pip"
    result = subprocess.run([pip_cmd, "install", "--quiet", "-e", str(project_root)])
    if result.returncode != 0:
        print("Error: dependency update failed.")
        return result.returncode

    print("\nUpdate complete.")

    # If the runtime is running, offer to restart it
    pid_path = get_runtime_pid_file()
    pid = _read_pid(pid_path)
    if pid and _is_process_running(pid):
        answer = input("\nThe runtime is currently running. Restart it now? [Y/n] ")
        if answer.strip().lower() in ("", "y", "yes"):
            _stop_runtime()
            return _start_runtime(project_root)

    return 0


def _cmd_logs(lines: int = 50, follow: bool = True) -> int:
    import collections as _collections
    log_path = get_logs_file()
    print(f"Log: {log_path}")
    if not log_path.exists():
        print("Log file does not exist yet (runtime has not been started).")
        return 0
    if os.name == "nt":
        with log_path.open("r", encoding="utf-8", errors="replace") as fh:
            tail_lines = _collections.deque(fh, maxlen=lines)
        print("".join(tail_lines), end="")
        if follow:
            print("[Live tail not supported on Windows — use: Get-Content -Wait]")
        return 0
    cmd = ["tail", f"-n{lines}"] + (["-f"] if follow else []) + [str(log_path)]
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass
    return 0


def _start_runtime(project_root: Path) -> int:
    ensure_runtime_dirs()
    _cleanup_stale_runtime_files()
    pid_path = get_runtime_pid_file()
    lock_path = get_runtime_lock_file()
    log_path = get_logs_file()
    current_pid = _read_pid(pid_path)
    if current_pid and _is_process_running(current_pid):
        print(f"assistant-runtime appears to already be running (PID {current_pid}).")
        return 0
    _safe_unlink(pid_path)
    _safe_unlink(lock_path)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_handle:
        subprocess.Popen(
            [sys.executable, "-m", "app.main"],
            cwd=str(project_root),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    runtime_pid: int | None = None
    for _ in range(30):
        runtime_pid = _read_pid(pid_path)
        if runtime_pid and _is_process_running(runtime_pid):
            break
        time.sleep(0.1)

    if runtime_pid and _is_process_running(runtime_pid):
        print(f"Started assistant-runtime (PID {runtime_pid}).")
        print(f"Log: {log_path}")
        return 0

    lock_pid = _read_lock_pid(lock_path)
    if lock_pid and _is_process_running(lock_pid):
        print(f"Started assistant-runtime (lock PID {lock_pid}; runtime PID not confirmed yet).")
        print(f"Log: {log_path}")
        return 0

    print("assistant-runtime launch was requested, but startup could not be confirmed yet.")
    print(f"Log: {log_path}")
    return 1


def _stop_runtime() -> int:
    _cleanup_stale_runtime_files()
    pid_path = get_runtime_pid_file()
    lock_path = get_runtime_lock_file()
    pid = _read_pid(pid_path)
    if pid is None:
        print("assistant-runtime is not running (no PID file found).")
        _safe_unlink(lock_path)
        return 0
    if _is_process_running(pid):
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True, text=True)
            else:
                os.kill(pid, signal.SIGTERM)
        except OSError as exc:
            print(f"Failed to stop assistant-runtime (PID {pid}): {exc}")
            return 1
        for _ in range(20):
            if not _is_process_running(pid):
                break
            time.sleep(0.1)
        print(f"Stopped assistant-runtime (PID {pid}).")
    else:
        print("assistant-runtime PID file was stale.")
    _safe_unlink(pid_path)
    _safe_unlink(lock_path)
    return 0


def _status_runtime() -> int:
    pid_path = get_runtime_pid_file()
    lock_path = get_runtime_lock_file()
    log_path = get_logs_file()
    pid = _read_pid(pid_path)
    lock_pid = _read_lock_pid(lock_path)

    if pid is not None and _is_process_running(pid):
        print(f"assistant-runtime is running (PID {pid}).")
        print(f"PID file: {pid_path}")
        print(f"Lock file: {lock_path}")
        print(f"Log file: {log_path}")
        return 0

    if lock_pid is not None and _is_process_running(lock_pid):
        print(f"assistant-runtime appears to be running (lock PID {lock_pid}).")
        print(f"PID file: {pid_path}")
        print(f"Lock file: {lock_path}")
        print(f"Log file: {log_path}")
        return 0

    if pid is None and lock_pid is None:
        print("assistant-runtime is not running.")
        print(f"PID file: {pid_path}")
        print(f"Lock file: {lock_path}")
        print(f"Log file: {log_path}")
        return 0

    print("assistant-runtime is not running, but stale runtime state exists.")
    print(f"PID file: {pid_path}")
    print(f"Lock file: {lock_path}")
    print(f"Log file: {log_path}")
    return 1


# ---------------------------------------------------------------------------
# Add agent wizard
# ---------------------------------------------------------------------------

def _run_add_agent(name: str, *, config_path: Path) -> int:
    """Interactive wizard for creating a new agent."""
    import json
    import re
    from .agent_manager import AgentManager, AgentManagerError
    from .config import load_config

    BOLD = "\033[1m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    RESET = "\033[0m"

    def ok(msg: str) -> None:
        print(f"  {GREEN}✓{RESET} {msg}")

    def warn(msg: str) -> None:
        print(f"  {YELLOW}!{RESET} {msg}")

    def step(title: str) -> None:
        print(f"\n{BOLD}{title}{RESET}")
        print("─" * 50)

    print()
    print(f"{BOLD}╔══════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}║      assistant-runtime  ·  New Agent             ║{RESET}")
    print(f"{BOLD}╚══════════════════════════════════════════════════╝{RESET}")

    # ── Step 1: Validate name ────────────────────────────────────────────────
    step("Step 1 — Agent name")

    cleaned = name.strip().lower()
    if not re.match(r'^[a-z0-9-]+$', cleaned):
        print(f"  Error: '{cleaned}' is not a valid agent name.")
        print("  Use lowercase letters, numbers, and dashes only (e.g. 'research', 'my-agent').")
        return 1

    try:
        config = load_config(config_path)
    except Exception as exc:
        print(f"  Error loading config: {exc}")
        return 1

    manager = AgentManager(project_root=config.project_root, agents_dir=config.agents_dir)
    agent_dir = config.agents_dir / cleaned
    if agent_dir.exists():
        print(f"  Error: An agent named '{cleaned}' already exists.")
        print("  Use 'assistant list-agents' to see existing agents.")
        return 1

    ok(f"Name: {cleaned}")

    # ── Step 2: Model ────────────────────────────────────────────────────────
    step("Step 2 — Model")

    models = [
        ("default", "Use global config default (recommended)"),
        ("claude-haiku-4-5", "Haiku — fastest, most efficient"),
        ("claude-sonnet-4-5", "Sonnet — balanced speed and capability"),
        ("claude-opus-4-5", "Opus — most capable, slowest"),
    ]
    print("  Which Claude model should this agent use?\n")
    for i, (model_id, desc) in enumerate(models, 1):
        marker = " (recommended)" if i == 1 else ""
        print(f"    {i}. {desc}{marker}")
    print()

    chosen_model: str | None = None
    while True:
        raw = input("  Choice [1]: ").strip() or "1"
        if raw.isdigit() and 1 <= int(raw) <= len(models):
            idx = int(raw) - 1
            chosen_model = None if idx == 0 else models[idx][0]
            ok(f"Model: {models[idx][0]}")
            break
        print("  Please enter a number between 1 and", len(models))

    # ── Step 3: Effort ───────────────────────────────────────────────────────
    step("Step 3 — Effort")

    efforts = [
        ("default", "Use global config default (recommended)"),
        ("low", "Low — faster, cheaper"),
        ("medium", "Medium — balanced"),
        ("high", "High — most thorough"),
    ]
    print("  What effort level should this agent use?\n")
    for i, (effort_id, desc) in enumerate(efforts, 1):
        marker = " (recommended)" if i == 1 else ""
        print(f"    {i}. {desc}{marker}")
    print()

    chosen_effort: str | None = None
    while True:
        raw = input("  Choice [1]: ").strip() or "1"
        if raw.isdigit() and 1 <= int(raw) <= len(efforts):
            idx = int(raw) - 1
            chosen_effort = None if idx == 0 else efforts[idx][0]
            ok(f"Effort: {efforts[idx][0]}")
            break
        print("  Please enter a number between 1 and", len(efforts))

    # ── Step 4: Channel ──────────────────────────────────────────────────────
    step("Step 4 — Communication channel")

    existing_accounts = list(config.accounts.keys())
    print("  Currently configured channels:")
    for acct_id, acct in config.accounts.items():
        print(f"    • {acct_id}  ({acct.platform})")
    print()
    print("    1. Use existing channels (agent will be reachable on all current bots)")
    print("    2. Add a dedicated channel with a new bot token")
    print()

    new_channel_summary = "existing channels"
    new_account_entry: dict | None = None

    while True:
        raw = input("  Choice [1]: ").strip() or "1"
        if raw in ("1", "2"):
            break
        print("  Please enter 1 or 2.")

    if raw == "2":
        print()
        print("  Platform:")
        print("    1. Telegram")
        print("    2. Discord")
        print("    3. Slack")
        print()

        platform_map = {"1": "telegram", "2": "discord", "3": "slack"}
        while True:
            p = input("  Choice [1]: ").strip() or "1"
            if p in platform_map:
                platform = platform_map[p]
                break
            print("  Please enter 1, 2, or 3.")

        print()
        token = _prompt_required(f"  {platform.capitalize()} bot token", secret=True)
        chat_ids_raw = _prompt_required("  Allowed chat IDs (comma-separated)")
        chat_ids = [c.strip() for c in chat_ids_raw.split(",") if c.strip()]

        channel_config: dict | None = None
        if platform == "slack":
            app_token = _prompt_required("  Slack app token (xapp-...)", secret=True)
            channel_config = {"app_token": app_token}

        new_account_entry = {
            "platform": platform,
            "token": token,
            "allowed_chat_ids": chat_ids,
        }
        if channel_config:
            new_account_entry["channel_config"] = channel_config

        new_channel_summary = f"new {platform.capitalize()} bot (token ending ...{token[-4:]})"
        ok(f"Channel: {new_channel_summary}")
    else:
        ok("Channel: using existing channels")

    # ── Step 5: Create files ─────────────────────────────────────────────────
    step("Step 5 — Creating agent files")

    try:
        agent_path = manager.create_agent(cleaned)
    except AgentManagerError as exc:
        print(f"  Error: {exc}")
        return 1

    # Overwrite agent.json if non-default model/effort were chosen
    if chosen_model is not None or chosen_effort is not None:
        agent_json_path = agent_path / "agent.json"
        try:
            with agent_json_path.open("r", encoding="utf-8") as fh:
                agent_json = json.load(fh)
        except Exception:
            agent_json = {}
        if chosen_model is not None:
            agent_json["model"] = chosen_model
        if chosen_effort is not None:
            agent_json["effort"] = chosen_effort
        with agent_json_path.open("w", encoding="utf-8") as fh:
            json.dump(agent_json, fh, indent=2)
            fh.write("\n")

    ok(f"Agent files created at {agent_path}")

    # Write new account/routing to config if requested
    if new_account_entry is not None:
        try:
            raw_cfg = load_raw_config(config_path)
            existing_accts = raw_cfg.get("accounts", {})
            existing_routing = raw_cfg.get("routing", {})
            existing_accts[cleaned] = new_account_entry
            existing_routing[cleaned] = {"default_agent": cleaned, "chat_agent_map": {}}
            update_config_values(config_path, {
                "accounts": existing_accts,
                "routing": existing_routing,
            })
            ok("Channel config written to config.json")
        except Exception as exc:
            warn(f"Could not update config.json: {exc}")
            warn("You can add the channel manually with 'assistant configure'.")

    # ── Step 6: Summary ──────────────────────────────────────────────────────
    print()
    print(f"{BOLD}{'─' * 50}{RESET}")
    print(f"{BOLD}Agent '{cleaned}' is ready.{RESET}")
    print()
    print(f"  Model:   {chosen_model or 'global default'}")
    print(f"  Effort:  {chosen_effort or 'global default'}")
    print(f"  Channel: {new_channel_summary}")
    print()
    print("  Next steps:")
    print(f"    Edit  agents/{cleaned}/AGENT.md  to shape its personality")
    print(f"    Edit  agents/{cleaned}/USER.md   to add context about yourself")
    print(f"    Then switch to it in chat:  /agent switch {cleaned}")
    print()
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    project_root = _project_root()
    config_path = get_config_file()

    if args.command == "chat":
        from .chat_session import TerminalChatSession

        try:
            session = TerminalChatSession(
                agent_name=args.agent,
                chat_id=args.chat_id,
            )
            session.run()
        except RuntimeError as exc:
            print(f"Error: {exc}")
            return 1
        return 0

    if args.command == "init":
        return _run_init(project_root)

    if args.command == "configure":
        return _run_configure(project_root)

    if args.command == "manage":
        command = [sys.executable, str(project_root / "app" / "manage.py"), *args.manage_args]
        return subprocess.call(command, cwd=str(project_root))

    if args.command == "doctor":
        print()
        result = _run_doctor(config_path, fix=args.fix, project_root=project_root)
        print()
        if args.fix and result == 0:
            print("  All checks passed.")
        elif result != 0:
            print("  Some checks failed. Run 'assistant doctor --fix' to attempt auto-repair.")
        print()
        return result

    if args.command == "start":
        return _start_runtime(project_root)

    if args.command == "stop":
        return _stop_runtime()

    if args.command == "restart":
        _stop_runtime()
        return _start_runtime(project_root)

    if args.command == "logs":
        return _cmd_logs(lines=args.lines, follow=not args.no_follow)

    if args.command == "update":
        return _cmd_update(project_root)

    if args.command == "status":
        return _status_runtime()

    if args.command == "test":
        print("Test commands:")
        print(f"- Windows: powershell -ExecutionPolicy Bypass -File {project_root / 'scripts' / 'test.ps1'}")
        print(f"- Mac/Linux: {project_root / 'scripts' / 'test.sh'}")
        print("- Direct: python -m pytest")
        return 0

    if args.command == "ui":
        from .web.server import WebDashboard

        dashboard = WebDashboard(host=args.host, port=args.port)
        try:
            dashboard.start(blocking=True)
        except OSError as exc:
            print(f"Failed to start web dashboard: {exc}")
            return 1
        return 0

    if args.command == "mcp":
        from .mcp_server import run_stdio

        run_stdio()
        return 0

    if args.command == "uninstall":
        return _run_uninstall(yes=args.yes, project_root=project_root)

    if args.command == "daemon":
        from .daemon_service import autostart_status, install_autostart, uninstall_autostart
        if args.daemon_action == "install":
            print(install_autostart(project_root))
            return 0
        if args.daemon_action == "uninstall":
            print(uninstall_autostart())
            return 0
        if args.daemon_action == "status":
            print(autostart_status())
            return 0

    # ── Short agent commands ─────────────────────────────────────────────────
    if args.command == "add":
        return _run_add_agent(args.name, config_path=config_path)

    if args.command == "restore":
        from .agent_manager import AgentManager, AgentManagerError
        from .config import load_config
        try:
            config = load_config(config_path)
        except Exception as exc:
            print(f"Error loading config: {exc}")
            return 1
        manager = AgentManager(project_root=config.project_root, agents_dir=config.agents_dir)
        try:
            restored = manager.restore_agent(args.name, restored_name=args.restored_name)
            print(f"Restored '{args.name}' → {restored.name}")
            return 0
        except AgentManagerError as exc:
            print(f"Error: {exc}")
            return 1

    if args.command in ("list-agents", "show", "clone", "rename", "delete"):
        from .agent_manager import AgentManager, AgentManagerError
        from .config import load_config
        try:
            config = load_config(config_path)
        except Exception as exc:
            print(f"Error loading config: {exc}")
            return 1
        manager = AgentManager(project_root=config.project_root, agents_dir=config.agents_dir)
        try:
            if args.command == "list-agents":
                agents = manager.list_agents()
                if not agents:
                    print("No agents found.")
                    return 0
                for a in agents:
                    desc = a.config.description or a.config.display_name or ""
                    suffix = f"  — {desc}" if desc else ""
                    model = a.config.model or "default"
                    effort = a.config.effort or "default"
                    print(f"  {a.name}{suffix}")
                    print(f"    model={model}  effort={effort}")
                return 0

            if args.command == "show":
                a = manager.show_agent(args.name)
                print(f"Name:        {a.name}")
                print(f"Path:        {a.path}")
                print(f"Display:     {a.config.display_name or '(none)'}")
                print(f"Description: {a.config.description or '(none)'}")
                print(f"Model:       {a.config.model or '(global default)'}")
                print(f"Effort:      {a.config.effort or '(global default)'}")
                print(f"AGENT.md:    {a.has_agent_md}")
                print(f"USER.md:     {a.has_user_md}")
                print(f"MEMORY.md:   {a.has_memory_md}")
                print(f"TOOLS.md:    {a.has_tools_md}")
                return 0

            if args.command == "clone":
                path = manager.clone_agent(args.source, args.target)
                print(f"Cloned '{args.source}' → '{args.target}'")
                print(f"Path: {path}")
                return 0

            if args.command == "rename":
                path = manager.rename_agent(args.source, args.target)
                print(f"Renamed '{args.source}' → '{args.target}'")
                return 0

            if args.command == "delete":
                if not args.yes:
                    confirm = input(
                        f"Archive agent '{args.name}'? "
                        "This can be undone with 'assistant restore'. [y/N] "
                    )
                    if confirm.strip().lower() != "y":
                        print("Cancelled.")
                        return 0
                archived = manager.delete_agent(args.name)
                print(f"Agent '{args.name}' archived to {archived}")
                return 0

        except AgentManagerError as exc:
            print(f"Error: {exc}")
            return 1

    _print_quick_help()
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
