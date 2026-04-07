# assistant-runtime

Standalone personal assistant runtime powered by Claude Code and designed to recreate the richer OpenClaw experience without paid model APIs.

## Current status

Phase 1A through early multi-agent are in place:
- Telegram polling and replies
- Claude Code subprocess execution
- agent context loading
- transcript persistence
- daily note persistence
- basic commands
- recent transcript context
- per-chat locking
- single-instance lock
- Windows helper scripts
- multi-agent-ready layout
- second example agent (`builder`)
- cross-platform agent management CLI
- early `assistant` command surface
- per-agent structured config with runtime overrides
- `/agent info <name>`
- Mac/Linux start/stop/status wrappers
- project-root `assistant.ps1` and `assistant.sh` launchers
- clone/rename/archive-restore agent lifecycle commands
- chat-to-agent routing with pinned-chat behavior

## Goals

- Telegram-first assistant
- Claude Code as the reasoning engine
- file-based memory and transcripts
- multi-agent-ready design
- sustainable, inspectable runtime

## Basic commands

- `/status`
- `/agents`
- `/agent`
- `/agent switch <name>`
- `/session reset`

## Primary CLI

The project now has a real package entry point:

- `assistant`

Primary installed commands:

```bash
assistant configure
assistant doctor
assistant start
assistant status
assistant stop
assistant manage list-agents
assistant test
```

If you are working from the repo without installing yet, the project-root launchers still work:

### Windows PowerShell

```powershell
powershell -ExecutionPolicy Bypass -File .\assistant.ps1 configure
powershell -ExecutionPolicy Bypass -File .\assistant.ps1 doctor
powershell -ExecutionPolicy Bypass -File .\assistant.ps1 start
powershell -ExecutionPolicy Bypass -File .\assistant.ps1 status
powershell -ExecutionPolicy Bypass -File .\assistant.ps1 stop
powershell -ExecutionPolicy Bypass -File .\assistant.ps1 manage list-agents
```

### Mac/Linux

```bash
./assistant.sh configure
./assistant.sh doctor
./assistant.sh start
./assistant.sh status
./assistant.sh stop
./assistant.sh manage list-agents
```

## Agent management

Examples:

```bash
assistant manage list-agents
assistant manage create-agent ops
assistant manage show-agent builder
assistant manage clone-agent builder builder-copy
assistant manage rename-agent builder-copy builder-lab
assistant manage delete-agent ops --yes
assistant manage list-archived-agents
assistant manage restore-agent ops-20260101-120000 --as ops
```

Lower-level helper scripts still exist for repo-local development, but the intended operator-facing interface is now the `assistant` command.

## Config paths

The canonical runtime config now lives in the user app config directory via the `assistant` path helper.

Current defaults:
- Windows: `%APPDATA%\assistant\config.json`
- macOS: `~/Library/Application Support/assistant/config/config.json`
- Linux: `~/.config/assistant/config.json`

When `assistant configure` writes config, it also seeds:
- `project_root`
- `agents_dir`
- `shared_dir`

That lets config live in a normal app-owned location while the runtime still knows where the repo resources live.

Relative path overrides are still supported if you want to customize behavior.

## Accounts and routing

The runtime now supports an OpenClaw-ish split between:
- **accounts** = external transport identities (for example Telegram bot tokens)
- **routing** = which agent handles chats on each account

Example config shape:

```json
{
  "accounts": {
    "primary": {
      "platform": "telegram",
      "token": "TOKEN_MAIN",
      "allowed_chat_ids": ["6390668081"]
    },
    "builder-bot": {
      "platform": "telegram",
      "token": "TOKEN_BUILDER",
      "allowed_chat_ids": ["6390668081"]
    }
  },
  "routing": {
    "primary": {
      "default_agent": "main",
      "chat_agent_map": {
        "6390668081": "main"
      }
    },
    "builder-bot": {
      "default_agent": "builder",
      "chat_agent_map": {
        "6390668081": "builder"
      }
    }
  }
}
```

Routing precedence inside an account is:
1. account-local config-pinned chat agent
2. account-local session-selected agent for that chat
3. account-local default agent

Behavior notes:
- pinned chats ignore manual `/agent switch` requests
- session selection is scoped by account + chat
- `/agent` and `/status` show the current account
- old single-bot config is still supported and normalizes internally to a `primary` account

## Provider config

Global config now supports:

```json
{
  "model_provider": "claude-code"
}
```

Only `claude-code` is implemented right now. This is groundwork for future providers such as OpenAI later.

## Agent config

Each agent can include:

```text
agents/<name>/agent.json
```

Example:

```json
{
  "display_name": "Builder",
  "description": "Focused implementation and project-building assistant",
  "provider": "claude-code",
  "model": "opus",
  "effort": "high"
}
```

Behavior:
- `provider` falls back to global `model_provider` if omitted
- `model` and `effort` fall back to global config if omitted
- Telegram commands `/agents`, `/agent`, and `/agent info <name>` show agent metadata
- switching agents changes the effective provider/model/effort used by the runtime

## Quick install

| Platform | What to do |
|---|---|
| **macOS** | Double-click **`Mac Install.command`** in Finder |
| **Windows** | Double-click **`Windows Install.bat`** in File Explorer |

A Terminal or PowerShell window opens and walks you through the rest automatically.

---

## Mac setup

### Prerequisites

On a Mac, make sure you have:
- Homebrew available
- Claude Code CLI (`claude`) installed and authenticated
- this repo copied somewhere like `~/Projects/assistant-runtime`

### Important note about Python on Mac

The macOS system `python3` may be too old for this project.

The validated working path on macOS was:
- install Homebrew `python@3.12`
- create a project-local `.venv`
- run install/tests/runtime commands through that venv

### First-time setup

Install Python 3.12 if needed:

```bash
brew install python@3.12
```

Create and populate a local virtual environment from the repo root:

```bash
/opt/homebrew/bin/python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip setuptools wheel
python -m pip install -e . pytest
```

You can then validate the CLI with either:

```bash
.venv/bin/python -m app.assistant_cli --help
```

or, after installation if your shell can see the entry point:

```bash
assistant --help
```

### Configure

Recommended path:

```bash
.venv/bin/python -m app.assistant_cli configure
.venv/bin/python -m app.assistant_cli doctor
```

Repo launcher fallback:

```bash
./assistant.sh configure
./assistant.sh doctor
```

Then confirm the generated canonical config includes your real account settings.

Single-account legacy config is still accepted, but the preferred newer format is:
- `accounts.<account_id>.token`
- `accounts.<account_id>.allowed_chat_ids`
- `routing.<account_id>.default_agent`
- `routing.<account_id>.chat_agent_map`

Canonical Mac config path:

```bash
~/Library/Application\ Support/assistant/config/config.json
```

### Mac run flow

Validated venv-based flow:

```bash
.venv/bin/python -m app.assistant_cli start
.venv/bin/python -m app.assistant_cli status
.venv/bin/python -m app.assistant_cli manage list-agents
.venv/bin/python -m app.assistant_cli stop
```

Repo launcher fallback:

```bash
./assistant.sh start
./assistant.sh status
./assistant.sh manage list-agents
./assistant.sh stop
```

### Useful Mac paths

Canonical runtime paths on macOS:
- config: `~/Library/Application Support/assistant/config/config.json`
- state dir: `~/Library/Application Support/assistant/state/`
- log: `~/Library/Logs/assistant/runtime.log`

### Mac troubleshooting

If something fails first, check these in order:
- `/opt/homebrew/bin/python3.12 --version`
- `claude --help`
- `.venv/bin/python -m app.assistant_cli doctor`
- confirm the canonical config file has your real account token(s) and chat ID(s)
- inspect `~/Library/Logs/assistant/runtime.log`
- make sure only one machine is long-polling the same Telegram bot token during validation

If `python -m pip install -e .` fails under Homebrew Python with an externally-managed-environment error, use a local `.venv` as shown above rather than installing directly into Homebrew-managed site-packages.

### Current Mac confidence level

The first real Mac validation pass has now been completed successfully:
- editable install works in a local `.venv`
- full test suite passes on Mac
- runtime starts on Mac
- Telegram `/status` round-trip was confirmed from the Mac runtime

## Configure and doctor

Recommended operator flow:

```bash
assistant configure
assistant doctor
assistant start
assistant status
assistant stop
assistant test
```

`assistant doctor` checks:
- config file presence and loadability
- canonical config path
- project / agents / shared paths
- runtime PID / lock / log / session-state paths
- provider config
- Claude CLI availability
- default agent existence
- per-account routing targets that point to missing agents
- duplicate Telegram token reuse across configured accounts

`assistant configure` now:
- preserves current values when you press Enter
- masks the displayed bot token value in prompts
- strips placeholder template values from live config
- suggests running `assistant doctor` afterward

## Dev workflow

### Install test dependency

```bash
pip install pytest
```

### Run tests

From the project root:

```bash
python -m pytest
```

Or use the helper scripts:

```bash
./scripts/test.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

Current automated coverage focuses on:
- config loading
- config manager behavior
- agent config loading
- command behavior
- routing precedence
- agent lifecycle basics
- doctor checks

Manual testing is still useful for:
- Telegram round-trips
- Claude CLI execution
- installed `assistant start/status/stop` behavior

## Installation

**Prerequisites:**
- Git → git-scm.com/download/win (Windows) or pre-installed on Mac
- Python 3.12+ → python.org/downloads
- Claude CLI → claude.ai/code

**Mac/Linux:**
```bash
git clone https://github.com/BrandNewBrandon/assistant-runtime.git
cd assistant-runtime
./install.sh
```

**Windows:**
```
git clone https://github.com/BrandNewBrandon/assistant-runtime.git
cd assistant-runtime
Windows Install.bat
```

Then follow the setup prompts.

