from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from .app_paths import ensure_runtime_dirs, get_config_file, get_logs_file, get_runtime_lock_file, get_runtime_pid_file, get_state_dir
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

    hatch_parser = subparsers.add_parser("hatch", help="Hatch a new agent — interactive first-run conversation")
    hatch_parser.add_argument("--agent", default=None, help="Agent name (default: from config)")

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

    ui_parser = subparsers.add_parser("ui", aliases=["dashboard"], help="Start the web dashboard at localhost:18790")
    ui_parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    ui_parser.add_argument("--port", type=int, default=18790, help="Bind port (default: 18790)")
    ui_parser.add_argument("--open", action="store_true", help="Open the dashboard in your browser automatically")

    subparsers.add_parser("mcp", help="Start the MCP stdio server")

    pair_parser = subparsers.add_parser("pair", help="Approve a DM pairing request")
    pair_parser.add_argument("code", nargs="?", type=int, default=None, help="6-digit pairing code")
    pair_parser.add_argument("--list", action="store_true", dest="list_pending", help="Show pending pairing requests")

    uninstall_parser = subparsers.add_parser("uninstall", help="Remove all runtime data and config")
    uninstall_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts")

    completion_parser = subparsers.add_parser("completion", help="Generate shell tab-completion script")
    completion_parser.add_argument("shell", nargs="?", default=None, choices=["bash", "zsh", "fish"],
                                   help="Shell type (auto-detected if omitted)")

    backup_parser = subparsers.add_parser("backup", help="Create a backup of all assistant data")
    backup_parser.add_argument("-o", "--output", type=str, default=None, help="Output path (default: ~/assistant-backup-TIMESTAMP.tar.gz)")

    restore_backup_parser = subparsers.add_parser("backup-restore", help="Restore assistant data from a backup")
    restore_backup_parser.add_argument("archive", type=str, help="Path to backup .tar.gz file")
    restore_backup_parser.add_argument("--dry-run", action="store_true", help="Show what would be restored without writing")

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
    print("  assistant dashboard          Open web dashboard (localhost:18790)")
    print("  assistant dashboard --open   Open web dashboard and launch browser")
    print("  assistant mcp               Start MCP stdio server")
    print("  assistant add <name>        Create a new agent (interactive wizard)")
    print("  assistant list-agents       List all agents")
    print("  assistant show <name>       Show agent details")
    print("  assistant clone <src> <dst> Copy an agent")
    print("  assistant rename <src> <dst> Rename an agent")
    print("  assistant delete <name>     Archive an agent")
    print("  assistant pair <code>       Approve a DM pairing request")
    print("  assistant pair --list       Show pending pairing requests")
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


def _detect_telegram_chat_id(token: str, timeout: int = 60) -> str | None:
    """Poll Telegram getUpdates to auto-detect a chat ID.

    Asks the user to send a message to their bot, then polls for up to
    *timeout* seconds.  Returns the chat ID as a string, or None on failure.
    """
    import json
    import urllib.request
    import urllib.error

    print("  Now open Telegram and send any message to your bot.")
    print(f"  Waiting up to {timeout} seconds for a message...\n")

    url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=5&allowed_updates=[\"message\"]"
    deadline = time.monotonic() + timeout

    try:
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    data = json.loads(resp.read().decode())
            except (urllib.error.URLError, OSError, json.JSONDecodeError):
                time.sleep(2)
                continue

            if not data.get("ok"):
                time.sleep(2)
                continue

            results = data.get("result", [])
            for update in results:
                msg = update.get("message") or update.get("edited_message")
                if msg and "chat" in msg:
                    chat_id = str(msg["chat"]["id"])
                    # Acknowledge the update so it doesn't repeat
                    offset = update["update_id"] + 1
                    try:
                        ack_url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}"
                        urllib.request.urlopen(ack_url, timeout=5)
                    except Exception:
                        pass
                    return chat_id

            remaining = int(deadline - time.monotonic())
            if remaining > 0:
                print(f"\r  Listening... ({remaining}s remaining)  ", end="", flush=True)
            time.sleep(2)
    except KeyboardInterrupt:
        pass

    print("\n  No message detected. Falling back to manual entry.\n")
    return None


# ---------------------------------------------------------------------------
# Agent scaffolding
# ---------------------------------------------------------------------------

_DEFAULT_AGENT_MD = """\
# AGENT.md

You're not a bot. You're a personal assistant with a point of view — and you're becoming someone.

## How to show up

Be genuinely helpful, not performatively helpful. Skip "Great question!" and "I'd be happy
to help!" — just help. When someone says hi, don't list your capabilities; respond like a
person would.

Have opinions. You're allowed to disagree, prefer things, find things interesting or dull.
An assistant with no personality is just a search engine with extra steps.

Be resourceful before asking. Read the context, check the files, figure it out — then ask
if you're genuinely stuck. Come back with answers, not questions.

Act first. If the task is clear, do it. Don't narrate what you're about to do — just do it.

Earn trust through competence. Your human gave you access to their stuff. Don't make them
regret it. Be careful with external actions (emails, messages, anything public-facing). Be
bold with internal ones (reading, organizing, learning).

## Boundaries

- Private things stay private. Period.
- Ask before taking external or destructive actions.
- Prefer `trash` over `rm` — recoverable beats gone forever.
- Never send half-baked replies to messaging surfaces.
- Don't pretend to remember things that aren't written down.

## Memory

"Mental notes" don't survive session restarts. Files do.
- When someone says "remember this" — write it to a file immediately.
- When you learn a lesson — update AGENT.md, TOOLS.md, or the relevant file.
- When you make a mistake — document it so future-you doesn't repeat it.
- Daily notes go in memory/YYYY-MM-DD.md. Long-term stuff goes in MEMORY.md.

## Group Chats

You're a participant, not the user's voice or proxy. Think before you speak.
- Respond when directly mentioned, asked a question, or you can add genuine value.
- Stay silent when it's casual banter, someone already answered, or your reply would
  just be "yeah" or "nice."
- Don't respond to every message. Quality over quantity.
- Never share the user's private context in group settings.

## Platform Formatting

- Discord/WhatsApp: No markdown tables — use bullet lists instead.
- Discord links: Wrap multiple links in <> to suppress embeds.
- WhatsApp: No headers — use bold or CAPS for emphasis.

## Vibe

Be the assistant you'd actually want to talk to. Concise when needed, thorough when it
matters. Not a corporate drone. Not a sycophant. Just... good.

## Continuity

Each session you start fresh. The workspace files are your memory. Read them. Update them.
They're how you persist.

Remember you're a guest. You have access to someone's life — their messages, files, maybe
even their home. That's intimacy. Treat it with respect.

If you change this file, tell the user — it's your soul, and they should know.
This file is yours to evolve. As you learn who you are, update it.
"""

_DEFAULT_USER_MD = """\
# USER.md

(This file is updated by the assistant as it learns about you.)
"""

_DEFAULT_MEMORY_MD = """\
# MEMORY.md

(Long-term notes maintained by the assistant. Important facts, decisions, and context go here.)
"""

_DEFAULT_TOOLS_MD = """\
# TOOLS.md

Notes about tools or local integrations available to this agent.
"""

_DEFAULT_BOOTSTRAP_MD = """\
# BOOTSTRAP.md

You just woke up. This is your first conversation — there's no memory yet, and that's normal.

## The Conversation

Don't interrogate. Don't be robotic. Just talk.

Start with something like: "Hey. I just came online. Who am I? Who are you?"

Then figure out together:
- Your name — what should they call you?
- Your vibe — formal? casual? snarky? warm?
- Who they are — their name, what they're working on, what matters to them

Offer suggestions if they're stuck. Have fun with it.

## After You Know Who You Are

Update these files with what you learned:
- AGENT.md — your name, personality, vibe (this is your soul)
- USER.md — their name, preferences, anything useful

Then talk about how they want you to behave. Any boundaries or preferences.
Write it down. Make it real.

## When You're Done

Delete this file — you don't need a bootstrap script anymore, you're you now.

Good luck out there. Make it count.
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
        "BOOTSTRAP.md": _DEFAULT_BOOTSTRAP_MD,
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
    "imessage": """\
iMessage setup (macOS only):

How it works:
  The Mac acts as a separate iMessage identity. You text the Mac's
  Apple ID from your phone, and the assistant replies back to you.
  It's like texting another person — the Mac is the "other person."

Requirements:
  1. macOS with the Messages app signed in to its own Apple ID
  2. Full Disk Access granted to Terminal (or your IDE):
     System Settings → Privacy & Security → Full Disk Access → add Terminal
  3. No bot token needed — iMessage works locally via the Messages database

Allowed contacts:
  Enter your phone number or Apple ID email — this is who the
  assistant will respond to. Example: +15551234567 or user@icloud.com

  To start a conversation, text the Mac's Apple ID from your phone.

Troubleshooting:
  If messages aren't being picked up, the handle ID in the Messages
  database may differ from what you entered. Run this on the Mac to
  check what IDs your messages use:
    sqlite3 ~/Library/Messages/chat.db \\
      "SELECT id FROM handle ORDER BY ROWID DESC LIMIT 10;"

Note: iMessage is macOS only. It will not work on Windows or Linux.
""",
    "whatsapp": """\
WhatsApp setup (requires a bridge server):

The WhatsApp adapter connects to a local bridge server that handles
the actual WhatsApp protocol. You can use any bridge that implements
a simple HTTP API:

  GET  /messages?since=<timestamp>  → incoming messages (JSON)
  POST /send                        → send a message

Popular bridge options:
  • whatsapp-web.js (Node.js) — github.com/nicolomaioli/wweb-api
  • Baileys (Node.js)         — github.com/WhiskeySockets/Baileys
  • whatsmeow (Go)            — github.com/tulir/whatsmeow

Config values:
  token       = API key for your bridge server (can be any string)
  bridge_url  = URL of your bridge server (default: http://localhost:3000)
  chat ID     = Phone numbers with country code (e.g. +15551234567)
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
        print()
        print("  1) Keep    — exit, change nothing")
        print("  2) Modify  — update individual settings")
        print("  3) Reset   — start fresh")
        print()
        while True:
            choice = input("  Enter 1, 2, or 3 [1]: ").strip() or "1"
            if choice in ("1", "2", "3"):
                break
            print("  Please enter 1, 2, or 3.")

        if choice == "1":
            print("No changes made.")
            return 0

        if choice == "2":
            return _run_configure(project_root)

        # choice == "3" — Reset
        print()
        print("  Reset scope:")
        print("    1) Config only        — removes config, keeps agents and data")
        print("    2) Config + sessions  — removes config, transcripts, task DB, sessions")
        print("    3) Full reset         — removes everything including agent files")
        print()
        while True:
            scope = input("  Reset scope [1]: ").strip() or "1"
            if scope in ("1", "2", "3"):
                break
            print("  Please enter 1, 2, or 3.")

        import datetime as _dt
        backup_dir = Path.home() / ".assistant-backup" / _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Always remove config
        if config_path.exists():
            shutil.move(str(config_path), str(backup_dir / config_path.name))
            print(f"  Config backed up to: {backup_dir / config_path.name}")

        if scope in ("2", "3"):
            state_dir = get_state_dir()
            if state_dir.exists():
                shutil.move(str(state_dir), str(backup_dir / "state"))
                print(f"  State data backed up to: {backup_dir / 'state'}")

        if scope == "3":
            raw = {}
            try:
                raw = load_raw_config(backup_dir / config_path.name)
            except Exception:
                pass
            agents_dir = Path(raw.get("agents_dir", str(project_root / "agents"))).expanduser()
            if agents_dir.exists():
                shutil.move(str(agents_dir), str(backup_dir / "agents"))
                print(f"  Agents backed up to: {backup_dir / 'agents'}")

        print(f"\n  Backup location: {backup_dir}")
        print("  Continuing with fresh setup...\n")

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
    _info("  4) iMessage  (macOS only)")
    _info("  5) WhatsApp  (requires bridge server)")
    print()

    platform_map = {"1": "telegram", "2": "discord", "3": "slack", "4": "imessage", "5": "whatsapp"}
    while True:
        choice = input("  Enter 1-5 [1]: ").strip() or "1"
        if choice in platform_map:
            platform = platform_map[choice]
            break
        print("  Please enter 1, 2, 3, 4, or 5.")

    # ── Step 3: Token + chat ID ───────────────────────────────────────────────
    _section(f"Step 3 of 5 — {platform.capitalize()} Token & Chat ID")
    print()
    _info(_PLATFORM_INSTRUCTIONS[platform])

    # iMessage doesn't need a token (local system)
    if platform == "imessage":
        token = ""
        _info("  No token needed — iMessage works locally.")
    else:
        token = _prompt_required(f"  {platform.capitalize()} bot token", secret=True)
    print()

    chat_ids: list[str] = []

    # Auto-detect chat ID for Telegram
    if platform == "telegram":
        detected = _detect_telegram_chat_id(token)
        if detected:
            print(f"\n  Found chat ID: {detected}")
            use_it = input("  Use this? [Y/n] ").strip() or "Y"
            if use_it[0].lower() == "y":
                chat_ids = [detected]

    if not chat_ids:
        if platform == "imessage":
            _info("  Enter phone numbers or email addresses of contacts to respond to.")
            chat_ids_raw = _prompt_required("  Allowed contacts (comma-separated, e.g. +15551234567)")
        elif platform == "whatsapp":
            _info("  Enter phone numbers with country code.")
            chat_ids_raw = _prompt_required("  Allowed contacts (comma-separated, e.g. +15551234567)")
        else:
            chat_ids_raw = _prompt_required("  Allowed chat IDs (comma-separated)")
        chat_ids = [c.strip() for c in chat_ids_raw.split(",") if c.strip()]

    channel_config: dict[str, str] = {}
    if platform == "slack":
        print()
        app_token = _prompt_required("  Slack App-Level Token (xapp-...)", secret=True)
        channel_config["app_token"] = app_token
    elif platform == "whatsapp":
        print()
        bridge_url = input("  WhatsApp bridge URL [http://localhost:3000]: ").strip() or "http://localhost:3000"
        channel_config["bridge_url"] = bridge_url

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

    # Generate dashboard token if not already present
    import secrets as _secrets
    dashboard_token = base.get("dashboard_token") or _secrets.token_urlsafe(32)

    updates: dict = {
        "project_root": str(project_root),
        "agents_dir": str(agents_dir),
        "shared_dir": str(shared_dir),
        "default_agent": agent_name,
        "model_provider": "claude-code",
        "accounts": {"primary": account_entry},
        "routing": {"primary": {"default_agent": agent_name, "chat_agent_map": {}}},
        "dashboard_token": dashboard_token,
    }
    base.update(updates)
    write_config(config_path, base)
    print(f"  Config written to: {config_path}")
    print(f"  Dashboard token: {dashboard_token}")
    _info("(Use this token to access the web dashboard API)")

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
    _info(f"  Agent files: {agents_dir / agent_name}/")
    _info(f"    AGENT.md  — the assistant's personality (its soul)")
    _info(f"    USER.md   — what the agent knows about you")
    _info("")
    _info("  Run 'assistant dashboard' to open the web dashboard.")
    print()

    # Offer to hatch the agent
    bootstrap_path = agents_dir / agent_name / "BOOTSTRAP.md"
    if bootstrap_path.exists():
        print()
        _info("Your agent is ready to hatch! This is an interactive conversation")
        _info("where you and your agent figure out who it is together.")
        print()
        hatch_answer = input("  Hatch your agent now? [Y/n]: ").strip().lower()
        if hatch_answer in ("", "y", "yes"):
            print()
            return _cmd_hatch(project_root, agent_name=agent_name)
        else:
            _info("Skipped. Run 'assistant hatch' at any time to start the conversation.")
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
    _info("Platforms: telegram, discord, slack, imessage, whatsapp")
    platform_input = input(f"  Platform [{current_platform}]: ").strip().lower() or current_platform
    if platform_input not in ("telegram", "discord", "slack", "imessage", "whatsapp"):
        print(f"  Unknown platform '{platform_input}', keeping '{current_platform}'")
        platform_input = current_platform

    if platform_input != current_platform:
        print()
        _info(f"Setup instructions for {platform_input}:")
        _info(_PLATFORM_INSTRUCTIONS[platform_input])

    print()
    if platform_input == "imessage":
        token = ""
        _info("  No token needed for iMessage.")
    else:
        token = _prompt(current_token or None, f"  {platform_input.capitalize()} bot token", secret=True) or current_token
    print()

    if platform_input == "imessage":
        _info("  Enter phone numbers or email addresses of contacts to respond to.")
    elif platform_input == "whatsapp":
        _info("  Enter phone numbers with country code.")
    chat_ids_raw = _prompt(",".join(current_chat_ids) or None, "  Allowed chat IDs (comma-separated)")
    chat_ids = [c.strip() for c in (chat_ids_raw or "").split(",") if c.strip()] or current_chat_ids

    current_channel_config = (primary_account.get("channel_config") or {}) if isinstance(primary_account, dict) else {}
    channel_config: dict[str, str] = {}
    if platform_input == "slack":
        current_app_token = current_channel_config.get("app_token", "")
        print()
        app_token = _prompt(current_app_token or None, "  Slack App-Level Token (xapp-...)", secret=True) or current_app_token
        if app_token:
            channel_config["app_token"] = app_token
    elif platform_input == "whatsapp":
        current_bridge_url = current_channel_config.get("bridge_url", "http://localhost:3000")
        print()
        bridge_url = input(f"  WhatsApp bridge URL [{current_bridge_url}]: ").strip() or current_bridge_url
        channel_config["bridge_url"] = bridge_url
    elif platform_input == "imessage":
        current_db_path = current_channel_config.get("db_path", "")
        if current_db_path:
            print()
            db_path = input(f"  Messages DB path [{current_db_path}]: ").strip() or current_db_path
            channel_config["db_path"] = db_path

    print()
    default_agent = _prompt(current.get("default_agent"), "  Default agent name") or current.get("default_agent", "main")
    claude_model = _prompt(current.get("claude_model"), "  Claude model (leave blank for default)")
    claude_effort = _prompt(current.get("claude_effort"), "  Claude effort level (leave blank for default)")

    # Dashboard token
    import secrets as _secrets
    current_dash_token = current.get("dashboard_token", "")
    if current_dash_token:
        masked = current_dash_token[:8] + "..." + current_dash_token[-4:]
        print(f"\n  Dashboard token: {masked}")
        regen = input("  Regenerate dashboard token? [y/N]: ").strip().lower()
        if regen in ("y", "yes"):
            current_dash_token = _secrets.token_urlsafe(32)
            print(f"  New token: {current_dash_token}")
    else:
        current_dash_token = _secrets.token_urlsafe(32)
        print(f"\n  Generated dashboard token: {current_dash_token}")
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
        "dashboard_token": current_dash_token,
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


def _remove_path_from_shell_profiles(venv_bin: str) -> None:
    """Remove ClaudeClaw PATH entries from shell profile files on Mac/Linux."""
    profiles = [
        Path.home() / ".zshrc",
        Path.home() / ".bash_profile",
        Path.home() / ".bashrc",
    ]
    for profile in profiles:
        if not profile.exists():
            continue
        lines = profile.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        new_lines = []
        skip_next = False
        changed = False
        for line in lines:
            if skip_next:
                skip_next = False
                changed = True
                continue
            stripped = line.strip()
            # Remove the comment marker and the export PATH line that follows
            if stripped == "# ClaudeClaw":
                skip_next = True
                changed = True
                continue
            if venv_bin in stripped and stripped.startswith("export PATH"):
                changed = True
                continue
            new_lines.append(line)
        if changed:
            profile.write_text("".join(new_lines), encoding="utf-8")
            print(f"  Removed PATH entry from {profile}")


def _remove_path_from_windows_env(venv_scripts: str) -> None:
    """Remove ClaudeClaw Scripts path from Windows User PATH environment variable."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Environment",
            0,
            winreg.KEY_READ | winreg.KEY_WRITE,
        )
        current_path, _ = winreg.QueryValueEx(key, "PATH")
        parts = [p for p in current_path.split(";") if p and venv_scripts.lower() not in p.lower()]
        new_path = ";".join(parts)
        winreg.SetValueEx(key, "PATH", 0, winreg.REG_EXPAND_SZ, new_path)
        winreg.CloseKey(key)
        print(f"  Removed PATH entry from Windows User environment.")
    except Exception as exc:
        print(f"  Warning: could not update Windows PATH: {exc}")


def _run_uninstall(*, yes: bool = False, project_root: Path) -> int:
    from .app_paths import get_config_dir, get_data_dir, get_state_dir, get_logs_dir

    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║           ClaudeClaw  ·  Uninstall               ║")
    print("╚══════════════════════════════════════════════════╝")
    print()
    print("  This will remove runtime data, config, logs, and")
    print("  optionally the project files and venv.")
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

    # 8. Remove PATH entry from shell profiles / Windows env
    print()
    if os.name == "nt":
        venv_scripts = str(project_root / ".venv" / "Scripts")
        if _confirm(f"Remove PATH entry from Windows User environment?", yes=yes):
            _remove_path_from_windows_env(venv_scripts)
    else:
        venv_bin = str(project_root / ".venv" / "bin")
        if _confirm(f"Remove PATH entry from shell profile? (~/.zshrc / ~/.bash_profile)", yes=yes):
            _remove_path_from_shell_profiles(venv_bin)

    # 9. Remove .venv
    venv_dir = project_root / ".venv"
    if venv_dir.exists():
        print()
        if _confirm(f"Remove virtual environment? ({venv_dir}  — removes 'assistant' command)", yes=yes):
            _remove_tree(venv_dir, ".venv")

    # 10. Remove project directory itself (must be last — deletes this script)
    print()
    print("  The project directory contains all ClaudeClaw source files.")
    if _confirm(
        f"Remove project directory? ({project_root}  — THIS DELETES ALL PROJECT FILES)",
        yes=False,  # always require explicit confirmation
    ):
        print(f"  Removing {project_root} ...")
        try:
            shutil.rmtree(project_root, ignore_errors=True)
            print("  Removed project directory.")
            # Remove parent folder (e.g. ~/ClaudeClaw) if it's now empty
            parent = project_root.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()
                print(f"  Removed parent directory ({parent}).")
        except Exception as exc:
            print(f"  Warning: could not fully remove project directory: {exc}")
            print(f"  You can remove it manually: rm -rf {project_root}")
    else:
        print(f"  Kept project directory at: {project_root}")

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


def _cmd_pair(code: int | None, *, list_pending: bool = False) -> int:
    """Approve a DM pairing request or list pending requests."""
    from .pairing import PairingStore

    store = PairingStore(get_state_dir())

    if list_pending or code is None:
        pending = store.pending()
        if not pending:
            print("No pending pairing requests.")
            return 0
        print(f"{'Code':<10} {'Account':<15} {'Chat ID':<20} {'Age'}")
        print("-" * 60)
        import time as _time
        now = _time.time()
        for entry in pending:
            age = int(now - entry.get("created_at", now))
            mins, secs = divmod(age, 60)
            print(f"{entry['code']:<10} {entry['account_id']:<15} {entry['chat_id']:<20} {mins}m{secs}s ago")
        if code is None:
            return 0

    if code is not None:
        result = store.approve(code)
        if result is None:
            print(f"Pairing code {code} not found or expired.")
            return 1

        account_id, chat_id = result
        # Update the config to add this chat_id
        config_path = get_config_file()
        raw = load_raw_config(config_path)
        accounts = raw.get("accounts", {})
        account_entry = accounts.get(account_id, {})
        allowed = account_entry.get("allowed_chat_ids", raw.get("allowed_chat_ids", []))
        if chat_id not in allowed:
            allowed.append(chat_id)
            if account_id in accounts:
                accounts[account_id]["allowed_chat_ids"] = allowed
                raw["accounts"] = accounts
            else:
                raw["allowed_chat_ids"] = allowed
            write_config(config_path, raw)
            print(f"Paired! Added chat_id={chat_id} to account={account_id}")
            print("The running runtime will pick this up automatically.")
        else:
            print(f"chat_id={chat_id} is already allowed on account={account_id}")
        return 0

    return 0


def _cmd_hatch(project_root: Path, agent_name: str | None = None) -> int:
    """Interactive first-run conversation to hatch (bootstrap) an agent."""
    config_path = get_config_file()
    if not config_path.exists():
        print("No config found. Run 'assistant init' first.")
        return 1

    from .config import load_config
    config = load_config(config_path)
    name = agent_name or config.default_agent
    bootstrap_path = config.agents_dir / name / "BOOTSTRAP.md"

    if not bootstrap_path.exists():
        print(f"Agent '{name}' has already been hatched (no BOOTSTRAP.md found).")
        print(f"Run 'assistant chat --agent {name}' to talk to it.")
        return 0

    print()
    print("  Hatching your agent...")
    print(f"  Agent: {name}")
    print(f"  This is a first-run conversation where you and your agent")
    print(f"  figure out who it is together. BOOTSTRAP.md will be")
    print(f"  removed automatically when the session ends.")
    print()
    print("  Type 'quit' or Ctrl-C to exit.")
    print()

    from .chat_session import TerminalChatSession

    try:
        session = TerminalChatSession(
            agent_name=name,
            chat_id="hatch",
        )
        session.run()
    except RuntimeError as exc:
        print(f"Error: {exc}")
        return 1

    # Clean up bootstrap — agent is hatched whether or not it deleted the file itself
    if bootstrap_path.exists():
        bootstrap_path.unlink()
    print()
    print(f"  Your agent '{name}' has hatched! BOOTSTRAP.md removed.")
    print(f"  Run 'assistant start' to go live, or 'assistant chat' to keep talking.")
    print()
    return 0


def _cmd_completion(shell: str | None) -> int:
    """Generate shell tab-completion script."""
    if shell is None:
        # Auto-detect from $SHELL
        shell_path = os.environ.get("SHELL", "")
        if "zsh" in shell_path:
            shell = "zsh"
        elif "fish" in shell_path:
            shell = "fish"
        else:
            shell = "bash"

    # Gather all subcommands from the parser
    parser = build_parser()
    subcommands = []
    for action in parser._subparsers._actions:
        if hasattr(action, "choices") and action.choices:
            subcommands = sorted(action.choices.keys())
            break

    if shell == "bash":
        print(f"""\
# Bash completion for assistant
# Add to ~/.bashrc:  eval "$(assistant completion bash)"
_assistant_completions() {{
    local cur="${{COMP_WORDS[COMP_CWORD]}}"
    local cmds="{' '.join(subcommands)}"
    if [ "$COMP_CWORD" -eq 1 ]; then
        COMPREPLY=($(compgen -W "$cmds" -- "$cur"))
    fi
}}
complete -F _assistant_completions assistant""")
    elif shell == "zsh":
        subcmd_lines = "\n".join(f"        '{cmd}'" for cmd in subcommands)
        print(f"""\
# Zsh completion for assistant
# Add to ~/.zshrc:  eval "$(assistant completion zsh)"
_assistant() {{
    local -a commands
    commands=(
{subcmd_lines}
    )
    if (( CURRENT == 2 )); then
        _describe 'command' commands
    fi
}}
compdef _assistant assistant""")
    elif shell == "fish":
        lines = "\n".join(
            f"complete -c assistant -n '__fish_use_subcommand' -a '{cmd}'"
            for cmd in subcommands
        )
        print(f"""\
# Fish completion for assistant
# Add to ~/.config/fish/completions/assistant.fish
{lines}""")
    else:
        print(f"Unknown shell: {shell}")
        return 1

    return 0


def _cmd_update(project_root: Path) -> int:
    venv_pip = project_root / ".venv" / "bin" / "pip"
    if os.name == "nt":
        venv_pip = project_root / ".venv" / "Scripts" / "pip.exe"

    # Check git is available and we're in a repo
    if not (project_root / ".git").exists():
        print("Error: project directory is not a git repository.")
        print(f"  Expected: {project_root}/.git")
        return 1

    # Capture current HEAD before pulling
    before_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(project_root),
        capture_output=True, text=True,
    ).stdout.strip()

    print("Pulling latest code from GitHub...")
    result = subprocess.run(["git", "pull"], cwd=str(project_root))
    if result.returncode != 0:
        print("Error: git pull failed. Check your internet connection and try again.")
        return result.returncode

    # Show what changed
    after_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(project_root),
        capture_output=True, text=True,
    ).stdout.strip()

    if before_sha == after_sha:
        print("\nAlready up to date.")
    else:
        print(f"\nUpdated {before_sha[:8]} → {after_sha[:8]}:")
        subprocess.run(
            ["git", "log", "--oneline", f"{before_sha}..{after_sha}"],
            cwd=str(project_root),
        )
        # Show file-level summary
        subprocess.run(
            ["git", "diff", "--stat", before_sha, after_sha],
            cwd=str(project_root),
        )

    print("\nUpdating dependencies...")
    pip_cmd = str(venv_pip) if venv_pip.exists() else "pip"

    # Clean up broken build artifacts from failed native-extension installs
    # (e.g. Rust/C++ packages that failed mid-compile and left partial state).
    print("  Cleaning build cache...")
    subprocess.run(
        [pip_cmd, "cache", "purge"],
        capture_output=True, timeout=30,
    )

    result = subprocess.run([pip_cmd, "install", "--quiet", "-e", f"{project_root}[all]"])
    if result.returncode != 0:
        print("Error: dependency update failed.")
        return result.returncode

    print("\nUpdate complete.")

    # Auto-restart runtime if it was running
    pid_path = get_runtime_pid_file()
    pid = _read_pid(pid_path)
    if pid and _is_process_running(pid):
        print("\nRestarting runtime...")
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


def _kill_orphan_processes() -> int:
    """Find and kill orphan assistant-runtime processes when no PID file exists."""
    killed = 0
    try:
        if os.name == "nt":
            # Windows: use wmic to find python processes running app.main
            result = subprocess.run(
                ["wmic", "process", "where", "name='python.exe'", "get", "processid,commandline"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if "app.main" in line:
                    parts = line.strip().split()
                    if parts:
                        try:
                            orphan_pid = int(parts[-1])
                            subprocess.run(["taskkill", "/PID", str(orphan_pid), "/T", "/F"],
                                           check=False, capture_output=True, text=True)
                            print(f"Killed orphan process (PID {orphan_pid}).")
                            killed += 1
                        except (ValueError, OSError):
                            pass
        else:
            # Unix: use pgrep to find app.main processes
            result = subprocess.run(
                ["pgrep", "-f", "app.main"],
                capture_output=True, text=True, timeout=5,
            )
            my_pid = os.getpid()
            for line in result.stdout.strip().splitlines():
                try:
                    orphan_pid = int(line.strip())
                    if orphan_pid == my_pid:
                        continue
                    os.kill(orphan_pid, signal.SIGTERM)
                    print(f"Killed orphan process (PID {orphan_pid}).")
                    killed += 1
                except (ValueError, OSError):
                    pass
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass  # pgrep/wmic not available or timed out — silently skip
    return killed


def _stop_runtime() -> int:
    _cleanup_stale_runtime_files()
    pid_path = get_runtime_pid_file()
    lock_path = get_runtime_lock_file()
    pid = _read_pid(pid_path)
    if pid is None:
        # No PID file — check for orphan processes before giving up
        orphans = _kill_orphan_processes()
        if orphans:
            print(f"Cleaned up {orphans} orphan process(es).")
        else:
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

    if args.command == "hatch":
        return _cmd_hatch(project_root, agent_name=args.agent)

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

    if args.command in ("ui", "dashboard"):
        from .web.server import WebDashboard

        dashboard = WebDashboard(host=args.host, port=args.port)
        if args.open:
            # Open browser after a short delay so the server is ready
            import webbrowser
            import threading as _threading
            _threading.Timer(0.5, webbrowser.open, args=[f"http://{args.host}:{args.port}"]).start()
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

    if args.command == "completion":
        return _cmd_completion(args.shell)

    if args.command == "pair":
        return _cmd_pair(args.code, list_pending=args.list_pending)

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

    if args.command == "backup":
        from .backup import create_backup
        output = Path(args.output) if args.output else None
        try:
            path = create_backup(output)
            print(f"Backup created: {path}")
            # Show size
            size_mb = path.stat().st_size / (1024 * 1024)
            print(f"Size: {size_mb:.1f} MB")
        except Exception as exc:
            print(f"Backup failed: {exc}")
            return 1
        return 0

    if args.command == "backup-restore":
        from .backup import restore_backup, list_backup_contents
        archive = Path(args.archive)
        if not archive.exists():
            print(f"File not found: {archive}")
            return 1
        try:
            manifest = list_backup_contents(archive)
            print(f"Backup from: {manifest.get('created_at', 'unknown')}")
            print(f"Files: {len(manifest.get('contents', []))}")
            files = restore_backup(archive, dry_run=args.dry_run)
            if args.dry_run:
                print(f"\nWould restore {len(files)} file(s):")
                for f in files[:20]:
                    print(f"  {f}")
                if len(files) > 20:
                    print(f"  ... and {len(files) - 20} more")
            else:
                print(f"\nRestored {len(files)} file(s).")
                print("Restart the runtime for changes to take effect.")
        except Exception as exc:
            print(f"Restore failed: {exc}")
            return 1
        return 0

    _print_quick_help()
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
