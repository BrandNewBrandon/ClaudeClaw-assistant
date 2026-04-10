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
| `assistant ui [--port 18790]` | Open web dashboard |
| `assistant logs [-n 100] [--no-follow]` | Tail the runtime log |
| `assistant mcp` | Start MCP stdio server |
| `assistant pair [code]` | Approve a DM pairing request |
| `assistant pair --list` | List pending pairing requests |

---

## In-Chat Commands

### Session

| Command | Description |
|---------|-------------|
| `/new` `/reset` | Start a fresh session |
| `/compact` | Summarize and compress context |
| `/transcript [n]` | Show last n messages (default 6) |

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

### Scheduling

| Command | Description |
|---------|-------------|
| `/remind <time> <msg>` | Set a reminder (e.g., `10m`, `2h`) |
| `/tasks` | List pending tasks |
| `/cancel <id>` | Cancel a task |
| `/quiet [on\|off\|set HH:MM HH:MM]` | Quiet hours config |
| `/briefing [now\|on\|off\|set\|add\|remove]` | Briefing config |

### Info

| Command | Description |
|---------|-------------|
| `/status` | Runtime + agent health |
| `/tools` | List available tools |
| `/skills` | List installed skills |
| `/hooks` | Show hook registry |
| `/search <query>` | Web search |
| `/help` | Show all commands |

---

## Agent Directory Structure

```
agents/<name>/
  agent.json         # Config (model, effort, display_name, description)
  AGENT.md           # Personality / system prompt
  USER.md            # User context and preferences
  MEMORY.md          # Long-term consolidated notes
  TOOLS.md           # Tool integrations
  BOOTSTRAP.md       # First-run conversation script
  memory/            # Daily notes (YYYY-MM-DD.md)
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

---

## Config Reference (`config.json`)

### Core

| Field | Default | Description |
|-------|---------|-------------|
| `default_agent` | `"main"` | Primary agent name |
| `model_provider` | `"claude-code"` | Must be "claude-code" |
| `claude_model` | — | Global model override |
| `claude_effort` | — | Global effort override |
| `claude_timeout_seconds` | — | Claude execution timeout |
| `max_prompt_chars` | `24000` | Prompt character limit |

### Accounts

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
| `cache_ttl_seconds` | `300` | Cache expiry |
| `compaction_enabled` | `true` | Auto session compaction |
| `compaction_token_budget` | `12000` | Token threshold |
| `pairing_enabled` | `true` | DM pairing system |
| `consolidation_enabled` | `true` | Daily note consolidation |
| `consolidation_keep_days` | `3` | Days before consolidation |
| `semantic_search_enabled` | `true` | Semantic memory search (requires fastembed) |
| `briefing_enabled` | `false` | Scheduled briefings |
| `briefing_times` | `[9]` | Briefing hours (24h) |
| `quiet_hours_start` | — | Quiet start (HH:MM) |
| `quiet_hours_end` | — | Quiet end (HH:MM) |
| `dashboard_token` | `""` | Dashboard auth token |
| `cooldown_seconds_per_chat` | `0.0` | Per-chat rate limit |

---

## Essential Paths

### Mac / Linux

| Purpose | Path |
|---------|------|
| Config | `~/Library/Application Support/assistant/config/config.json` |
| Agents | `~/Library/Application Support/assistant/config/agents/` |
| Data | `~/Library/Application Support/assistant/data/` |
| State | `~/Library/Application Support/assistant/state/` |
| Logs | `~/Library/Logs/assistant/runtime.log` |
| PID file | `~/Library/Application Support/assistant/state/runtime.pid` |
| Sessions | `~/Library/Application Support/assistant/state/sessions.json` |
| Project | `~/ClaudeClaw/assistant/` |

### Windows

| Purpose | Path |
|---------|------|
| Config | `%APPDATA%\assistant\config\config.json` |
| Agents | `%APPDATA%\assistant\config\agents\` |
| Data | `%APPDATA%\assistant\data\` |
| State | `%APPDATA%\assistant\state\` |
| Logs | `%APPDATA%\assistant\logs\runtime.log` |
| Project | `%USERPROFILE%\ClaudeClaw\assistant\` |

**Override all paths:** set `ASSISTANT_APP_ROOT` environment variable.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No DM reply | `assistant pair --list` then `assistant pair <code>` |
| Silent in group chat | Bot must be mentioned or patterns must match |
| Runtime won't start | Check `assistant status` for stale PID, then `assistant stop` |
| Config errors | `assistant doctor --fix` |
| Claude not found | Install Claude CLI: `npm install -g @anthropic-ai/claude-code` |
| "Command line too long" (Windows) | Update to latest — fixed with stdin prompt passing |
| Dashboard won't open | Check port 18790: `assistant ui --port 18791` |
| Agent not responding | `assistant show <name>` — verify agent.json + AGENT.md exist |
| Stale sessions | `/new` to reset, or `/compact` to free context |
| Memory not working | `/consolidate` to merge daily notes |

---

## Web Dashboard

```
assistant ui                    # Start at localhost:18790
assistant ui --port 3000        # Custom port
assistant ui --host 0.0.0.0    # Expose on network
```

Dashboard token (optional): set `dashboard_token` in config.json.

---

## Doctor Checks

`assistant doctor` validates:

- Config file exists and parses
- Claude CLI is in PATH
- Default agent directory exists
- Agents and shared directories exist
- All account tokens are present and unique
- All routing entries point to real agents
- Allowed chat IDs are configured

`assistant doctor --fix` auto-repairs:

- Creates missing agents directory
- Scaffolds missing default agent
- Creates missing shared directory
