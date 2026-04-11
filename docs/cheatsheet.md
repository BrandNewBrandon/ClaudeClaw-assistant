# ClaudeClaw Cheat Sheet

---

## Quick Install

**Mac / Linux:**
```bash
git clone https://github.com/BrandNewBrandon/ClaudeClaw-assistant.git ~/ClaudeClaw/assistant && bash ~/ClaudeClaw/assistant/install.sh
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/BrandNewBrandon/ClaudeClaw-assistant.git $HOME\ClaudeClaw\assistant; & "$HOME\ClaudeClaw\assistant\install.ps1"
```

---

## CLI Commands

### Setup & Config

| Command | Description |
|---------|-------------|
| `assistant init` | First-time setup wizard |
| `assistant configure` | Reconfigure the runtime |
| `assistant doctor` | Check runtime health |
| `assistant doctor --fix` | Auto-repair common issues |
| `assistant update` | Pull latest code + update deps |
| `assistant uninstall [--yes]` | Remove all data, config, and files |
| `assistant completion [bash\|zsh\|fish]` | Generate shell tab-completion |

### Runtime Control

| Command | Description |
|---------|-------------|
| `assistant start` | Start the runtime |
| `assistant stop` | Stop the runtime |
| `assistant restart` | Stop and restart |
| `assistant status` | Check if running (PID, lock, log) |
| `assistant daemon install` | Register autostart on login |
| `assistant daemon uninstall` | Remove autostart |
| `assistant daemon status` | Show autostart registration |

### Agents

| Command | Description |
|---------|-------------|
| `assistant add <name>` | Create a new agent (interactive) |
| `assistant list-agents` | List all agents |
| `assistant show <name>` | Show agent details |
| `assistant clone <src> <dst>` | Copy an agent |
| `assistant rename <old> <new>` | Rename an agent |
| `assistant delete <name> [--yes]` | Archive an agent |
| `assistant restore <name> [--as <new>]` | Restore archived agent |
| `assistant hatch [--agent <name>]` | Run first-conversation bootstrap |

### Tools

| Command | Description |
|---------|-------------|
| `assistant chat [--agent <name>]` | Chat in the terminal |
| `assistant dashboard [--open]` | Open web dashboard |
| `assistant logs [-n 100] [--no-follow]` | Tail the runtime log |
| `assistant mcp` | Start MCP stdio server |
| `assistant pair [code]` | Approve a DM pairing request |
| `assistant pair --list` | List pending pairing requests |
| `assistant backup` | Create a backup archive |
| `assistant backup-restore <file>` | Restore from backup |
| `assistant backup-restore <file> --dry-run` | Preview restore |

---

## In-Chat Commands

### Session

| Command | Description |
|---------|-------------|
| `/new` `/reset` | Start a fresh session |
| `/compact` | Summarize and compress context |
| `/transcript [n]` | Show last n messages (default 6) |
| `/search-chat <query>` | Search conversation history |
| `/export` | Export transcript as text |

### Agents

| Command | Description |
|---------|-------------|
| `/agents` | List all agents |
| `/agent` | Current agent info |
| `/agent info <name>` | Detailed agent info |
| `/agent switch <name>` | Switch active agent |
| `/model [name]` | Show or change model |
| `/effort [low\|medium\|high]` | Show or change effort |

### Memory

| Command | Description |
|---------|-------------|
| `/remember <text>` | Save to daily notes |
| `/note <text>` | Alias for /remember |
| `/memory` | Show relevant memory snippets |
| `/consolidate [days]` | Merge daily notes into MEMORY.md |

### Scheduling & Tasks

| Command | Description |
|---------|-------------|
| `/remind <time> <msg>` | Set a reminder (e.g., `10m`, `2h`) |
| `/tasks` | List pending tasks |
| `/cancel <id>` | Cancel a task |
| `/quiet [on\|off\|set HH:MM HH:MM]` | Quiet hours config |
| `/briefing [now\|on\|off\|set\|add\|remove]` | Briefing config |

### Background Jobs

| Command | Description |
|---------|-------------|
| `/bg <prompt>` | Run a prompt in the background |
| `/every <interval> <prompt>` | Recurring background job (e.g., `/every 24h check PRs`) |
| `/jobs` | List all background jobs |
| `/job <id>` | Show job status and result |
| `/job cancel <id>` | Cancel a job |
| `/delegate <agent> <prompt>` | Delegate a task to another agent |

### Messaging

| Command | Description |
|---------|-------------|
| `/forward <target> <msg>` | Forward to another chat or surface |
| `/search <query>` | Web search |

### System

| Command | Description |
|---------|-------------|
| `/status` | Runtime + agent health |
| `/diagnostics` | Runtime metrics, thread health, error counts |
| `/tools` | List available tools |
| `/skills` | List installed skills |
| `/hooks` | Show hook registry |
| `/monitors [on\|off]` | System monitor status / toggle |
| `/help` | Show all commands |

### Claude Code Skills

| Command | Description |
|---------|-------------|
| `/cc-skills` | List available CC skills |
| `/cc-skill <name>` | Show skill details |
| `/cc-install <url>` | Install from GitHub (e.g., `owner/repo`) |
| `/cc-uninstall <name>` | Remove installed skill |
| `/cc-import <name>` | Enable a CC skill for your agents |
| `/cc-remove <name>` | Disable a CC skill |

---

## Agent Directory Structure

```
agents/<name>/
  agent.json         # Config (model, effort, display_name, etc.)
  AGENT.md           # Personality / system prompt
  USER.md            # User context and preferences
  MEMORY.md          # Long-term consolidated notes
  TOOLS.md           # Tool integrations
  BOOTSTRAP.md       # First-run conversation script
  memory/            # Daily notes (YYYY-MM-DD.md)
  documents/         # Saved PDF extractions
  sessions/          # Session transcripts
```

### agent.json fields

| Field | Example | Description |
|-------|---------|-------------|
| `display_name` | `"Builder"` | Human-friendly name |
| `description` | `"Coding assistant"` | Agent purpose |
| `model` | `"opus"` | Model override (sonnet/opus/haiku) |
| `effort` | `"high"` | Effort override (low/medium/high) |
| `provider` | `"claude-code"` | AI provider |
| `working_dir` | `"~/Projects"` | Shell working directory |
| `safe_commands` | `["git", "npm"]` | Commands that bypass approval |
| `computer_use` | `false` | Enable screen control tools |
| `computer_use_auto_approve` | `false` | Skip approval for actions |
| `cc_skills` | `["tdd"]` | Imported Claude Code skills |

---

## Config Reference (`config.json`)

### Core

| Field | Default | Description |
|-------|---------|-------------|
| `default_agent` | `"main"` | Primary agent name |
| `model_provider` | `"claude-code"` | Must be "claude-code" |
| `claude_model` | — | Global model override |
| `claude_effort` | — | Global effort override |
| `claude_timeout_seconds` | `300` | Claude execution timeout (1-600) |
| `max_prompt_chars` | `24000` | Prompt character limit |

### Accounts

Supported platforms: `telegram`, `discord`, `slack`, `imessage`, `whatsapp`

```json
{
  "accounts": {
    "primary": {
      "platform": "telegram",
      "token": "BOT_TOKEN",
      "allowed_chat_ids": ["123456"]
    }
  },
  "routing": {
    "primary": {
      "default_agent": "main",
      "chat_agent_map": {}
    }
  }
}
```

### Features

| Field | Default | Description |
|-------|---------|-------------|
| `cache_enabled` | `true` | Response cache |
| `cache_ttl_seconds` | `300` | Cache expiry (0-86400) |
| `cooldown_seconds_per_chat` | `0.0` | Per-chat rate limit (0-300) |
| `compaction_enabled` | `true` | Auto session compaction |
| `compaction_token_budget` | `12000` | Token threshold (1000-200000) |
| `pairing_enabled` | `true` | DM pairing system |
| `consolidation_enabled` | `true` | Daily note consolidation |
| `consolidation_keep_days` | `3` | Days before consolidation |
| `consolidation_hour` | `2` | Hour to run (0-23) |
| `semantic_search_enabled` | `true` | Semantic memory search |
| `embedding_model` | `"BAAI/bge-small-en-v1.5"` | Embedding model for search |
| `briefing_enabled` | `false` | Scheduled briefings |
| `briefing_times` | `[9]` | Briefing hours (0-23) |
| `quiet_hours_start` | — | Quiet start (HH:MM) |
| `quiet_hours_end` | — | Quiet end (HH:MM) |
| `dashboard_token` | (auto) | Dashboard auth token |
| `auto_memory` | `false` | Auto-extract facts from conversations |
| `session_reset_daily_hour` | — | Daily session reset hour (0-23) |
| `session_idle_reset_minutes` | — | Idle reset timeout |

---

## Tools Available to Agents

| Tool | Description |
|------|-------------|
| `web_search` | DuckDuckGo search |
| `web_fetch` | Fetch and extract page content |
| `read_file` | Read local files |
| `write_file` | Write local files |
| `list_dir` | Directory listing |
| `disk_usage` | Disk space stats |
| `list_processes` | Running processes |
| `run_command` | Shell execution (approval-gated) |
| `screenshot` | Capture screen (computer_use) |
| `mouse_click` | Click at coordinates (computer_use) |
| `mouse_move` | Move cursor (computer_use) |
| `keyboard_type` | Type text (computer_use) |
| `keyboard_hotkey` | Key combos (computer_use) |
| `scroll` | Scroll screen (computer_use) |
| `open_url` | Open URL in browser |
| `open_app` | Launch application |
| `get_screen_size` | Screen resolution |
| `get_mouse_position` | Cursor position |

---

## Essential Paths

### Mac / Linux

| Purpose | Path |
|---------|------|
| Config | `~/Library/Application Support/assistant/config/config.json` |
| Agents | `~/Library/Application Support/assistant/config/agents/` |
| State | `~/Library/Application Support/assistant/state/` |
| Logs | `~/Library/Logs/assistant/runtime.log` |
| CC Skills | `~/.assistant/cc-skills/` |
| User Skills | `~/.assistant/skills/` |

### Windows

| Purpose | Path |
|---------|------|
| Config | `%APPDATA%\assistant\config.json` |
| Agents | `%APPDATA%\assistant\config\agents\` |
| State | `%LOCALAPPDATA%\assistant\state\` |
| Logs | `%LOCALAPPDATA%\assistant\logs\runtime.log` |

**Override all paths:** set `ASSISTANT_APP_ROOT` environment variable.

---

## Webhook API

```bash
curl -X POST http://localhost:18790/api/webhook \
  -H "Authorization: Bearer YOUR_DASHBOARD_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text": "Deploy complete", "chat_id": "123", "agent": "main"}'
```

---

## Optional Dependencies

```bash
pip install assistant-runtime[discord]       # Discord
pip install assistant-runtime[slack]         # Slack
pip install assistant-runtime[semantic]      # Semantic memory search
pip install assistant-runtime[computer-use]  # Computer use tools
pip install assistant-runtime[voice]         # Voice memo transcription
pip install assistant-runtime[all]           # Everything
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No DM reply | `assistant pair --list` then `assistant pair <code>` |
| Runtime won't start | Check `assistant status`, then `assistant stop` |
| Config errors | `assistant doctor --fix` |
| Claude not found | Install Claude CLI: `claude.ai/code` |
| Dashboard won't open | Check port: `assistant dashboard --port 18791` |
| Agent not responding | `assistant show <name>` — verify files exist |
| Stale sessions | `/new` to reset, `/compact` to free context |
| Voice not working | `pip install openai-whisper` |
| Computer use missing | `pip install pyautogui Pillow` |
| iMessage no messages | Grant Full Disk Access to Terminal |
| WhatsApp offline | Check bridge server: `assistant doctor` |

---

## Doctor Checks

`assistant doctor` validates:

- Config file exists and parses
- Claude CLI is in PATH
- Default agent directory exists
- All routing entries point to real agents
- iMessage: macOS + Messages DB access
- WhatsApp: bridge server reachability
- pymupdf: PDF support available
- pyautogui: computer use ready (if enabled)
- fastembed: semantic search (if enabled)
- Config field ranges (timeouts, hours, etc.)
