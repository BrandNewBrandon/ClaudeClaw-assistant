# ClaudeClaw

A personal AI assistant runtime powered by Claude Code. Connects to your messaging apps, runs on your machine, keeps its own memory, and acts on your behalf.

## Status

**All phases complete (0–7). 253 tests passing.**

## Features

### Messaging (5 platforms)
- **Telegram** — polling + streaming responses with inline approval buttons
- **Discord** — WebSocket gateway via discord.py
- **Slack** — Socket Mode via slack-sdk
- **iMessage** — macOS native (reads Messages DB, sends via AppleScript)
- **WhatsApp** — HTTP bridge pattern (works with any bridge server)

### Tools
| Tool | What it does |
|------|-------------|
| `web_search` | DuckDuckGo search |
| `web_fetch` | Fetch and extract page content |
| `read_file` / `write_file` | Local file access |
| `list_dir` | Directory listing |
| `disk_usage` | Disk space stats |
| `list_processes` | Running processes |
| `run_command` | Shell execution (approval-gated) |
| `screenshot` | Capture screen (computer use) |
| `mouse_click` / `keyboard_type` | Screen interaction (computer use) |
| `open_url` / `open_app` | Launch browser/apps |

### Agents
- Multi-agent system with distinct personalities, memory, and routing
- Per-agent config: model, effort, safe commands, working directory
- Agent delegation (`/delegate <agent> <prompt>`)
- Builder agent — execution-biased coding persona

### Background Jobs
- `/bg <prompt>` — fire-and-forget with notification on completion
- Full tool access in background (web search, files, etc.)
- Up to 2 concurrent jobs with conversation context
- `/jobs`, `/job <id>`, `/job cancel <id>`

### Memory & Context
- Persistent transcripts (JSONL per chat)
- Daily notes + nightly memory consolidation
- Semantic search (fastembed embeddings) with keyword fallback
- Session compaction (auto-summarize old messages)
- Configurable embedding model

### Computer Use (opt-in)
- Screenshot, click, type, scroll, hotkeys — cross-platform via pyautogui
- Approval gate on action tools (configurable auto-approve per agent)
- 10 tool iterations for multi-step screen workflows

### PDF Document Q&A
- Drop a PDF into chat, ask questions
- Small PDFs (≤5 pages) inlined, larger ones saved to file
- Text extraction via pymupdf

### System Monitors
- Proactive disk usage and process count alerts
- 5-minute poll interval, 1-hour cooldown between alerts
- `/monitors on/off`

### Claude Code Skill Importer
- Import Claude Code skills/plugins into ClaudeClaw
- Install from GitHub: `/cc-install owner/repo`
- Enable per agent: `"cc_skills": ["tdd", "brainstorming"]`
- Skill instructions injected into agent prompt automatically

### Reliability
- SQLite persistence for tasks and jobs (survives restarts)
- Stale job recovery on startup
- Transcript rotation (auto-archive at 5000 lines)
- File write locks, SQLite timeouts
- Config permissions (0o600), field validation
- Polling failure tracking with escalated alerts
- Backup/restore (`assistant backup` / `assistant backup-restore`)

### Operator Tools
- Web dashboard (`assistant dashboard`)
- `/diagnostics` — runtime metrics, thread health, error counts
- `assistant doctor` — health checks for all platforms and dependencies
- Hooks system for custom event handling

## Quick Install

| Platform | What to do |
|---|---|
| **macOS** | Double-click **`Mac Install.command`** |
| **Windows** | Double-click **`Windows Install.bat`** |

Or from terminal:

**Mac/Linux:**
```bash
git clone https://github.com/BrandNewBrandon/ClaudeClaw-assistant.git ~/ClaudeClaw/assistant && bash ~/ClaudeClaw/assistant/install.sh
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/BrandNewBrandon/ClaudeClaw-assistant.git $HOME\ClaudeClaw\assistant; & "$HOME\ClaudeClaw\assistant\install.ps1"
```

The installer sets up Python, creates a virtual environment, and launches the setup wizard.

## Setup

```bash
assistant init
```

The wizard walks you through:
1. Choose platform (Telegram, Discord, Slack, iMessage, WhatsApp)
2. Enter credentials (bot token, chat IDs, etc.)
3. Name your agent
4. Optional: enable autostart

Reconfigure anytime: `assistant configure`

## Usage

```bash
assistant start          # Start the runtime
assistant stop           # Stop it
assistant status         # Check if running
assistant dashboard      # Open web dashboard
assistant chat           # Chat in terminal
assistant doctor         # Health check
assistant backup         # Create backup
```

### Chat Commands

| Command | What it does |
|---|---|
| `/status` | Runtime info |
| `/agents` | List agents |
| `/agent switch <name>` | Switch agent |
| `/bg <prompt>` | Background job |
| `/delegate <agent> <prompt>` | Delegate to agent |
| `/remind <time> <msg>` | Set reminder |
| `/search-chat <query>` | Search history |
| `/forward <target> <msg>` | Forward message |
| `/export` | Export transcript |
| `/diagnostics` | Runtime metrics |
| `/cc-skills` | List CC skills |
| `/cc-install <url>` | Install CC skill |
| `/help` | Full command list |

## Agent Config

```json
{
  "display_name": "Builder",
  "description": "Coding assistant",
  "model": "opus",
  "effort": "high",
  "working_dir": "~/Projects",
  "safe_commands": ["git", "npm", "pytest"],
  "computer_use": false,
  "computer_use_auto_approve": false,
  "cc_skills": ["tdd", "brainstorming"]
}
```

## Config Paths

| Platform | Location |
|---|---|
| macOS | `~/Library/Application Support/assistant/config/config.json` |
| Windows | `%APPDATA%\assistant\config.json` |
| Linux | `~/.config/assistant/config.json` |

## Documentation

- **[User Guide](GUIDE.md)** — full documentation
- **[Roadmap](docs/roadmap.md)** — project phases and milestones
- **[Cheat Sheet](docs/cheatsheet.md)** — quick reference

## Prerequisites

- Python 3.11+
- [Claude Code CLI](https://claude.ai/code) installed and authenticated
- A messaging platform bot (setup wizard helps with this)

## Optional Dependencies

```bash
pip install assistant-runtime[discord]       # Discord support
pip install assistant-runtime[slack]         # Slack support
pip install assistant-runtime[semantic]      # Semantic memory search
pip install assistant-runtime[computer-use]  # Computer use tools
pip install assistant-runtime[all]           # Everything
```
