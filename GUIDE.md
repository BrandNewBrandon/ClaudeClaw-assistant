# ClaudeClaw — User Guide

A personal AI assistant that runs on your computer and connects to your messaging apps.
It uses Claude (Anthropic's AI) as its brain and keeps its own memory between conversations.

---

## Table of Contents

1. [What it is](#what-it-is)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [First-time setup](#first-time-setup)
5. [Starting and stopping](#starting-and-stopping)
6. [Terminal commands](#terminal-commands)
7. [Chat commands](#chat-commands)
8. [Session compaction](#session-compaction)
9. [Session resets](#session-resets)
10. [Agent files](#agent-files)
11. [Web dashboard](#web-dashboard)
12. [Multiple agents](#multiple-agents)
13. [DM pairing](#dm-pairing)
14. [Hooks](#hooks)
15. [Troubleshooting](#troubleshooting)

---

## What it is

ClaudeClaw is a background program that:

- Connects to your Telegram (or Discord or Slack) account
- Listens for messages from you
- Sends your message to Claude for a reply
- Sends the reply back to you
- Remembers important things you tell it across conversations

Think of it as running your own private AI assistant — not a cloud service someone else controls,
but a program running on your own machine, using your own Claude account.

---

## Prerequisites

Before installing, you need two things:

### 1. Python 3.11 or newer

Check if you have it by opening a terminal and running:

```
python3 --version
```

If the version shown is lower than 3.11, or you get "command not found":

- **Mac:** Install via Homebrew — `brew install python@3.12`
  (Install Homebrew first from https://brew.sh if you don't have it)
- **Windows:** Download from https://www.python.org/downloads/
  When installing, check the box **"Add Python to PATH"**

### 2. Claude Code CLI

This is the command-line tool that lets the runtime talk to Claude.

- Download and install from: **https://claude.ai/code**
- After installing, open a new terminal and run `claude --version` to confirm it works
- Make sure you are logged in to your Anthropic account in Claude Code

### 3. A messaging app bot

You need to create a bot on whichever platform you want to use.
The setup wizard (covered below) walks you through this step by step.

The easiest platform to start with is **Telegram**.

---

## Installation

### One-liner install from GitHub

Open a terminal and paste one command:

**Mac / Linux:**
```bash
git clone https://github.com/BrandNewBrandon/assistant-runtime.git ~/ClaudeClaw/assistant && bash ~/ClaudeClaw/assistant/install.sh
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/BrandNewBrandon/assistant-runtime.git $HOME\ClaudeClaw\assistant; & "$HOME\ClaudeClaw\assistant\install.ps1"
```

This clones the project and runs the installer in one step. The setup wizard starts automatically at the end.

### Already have the files?

If you downloaded or cloned the project manually:

**macOS** — Double-click **`Mac Install.command`** in Finder.

**Windows** — Double-click **`Windows Install.bat`** in File Explorer.

**Or from the terminal:**

**Mac / Linux:**
```bash
cd ~/ClaudeClaw/assistant
bash install.sh
```

**Windows (PowerShell):**
```powershell
cd ~\ClaudeClaw\assistant
.\install.ps1
```

If you see a red error about scripts being disabled on Windows, run this once first:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

---

All installation methods do the same things:

1. Check that Python 3.11+ is available
2. Check that the `claude` CLI is installed
3. Create a private virtual environment (`.venv`) in the project folder
4. Install the `assistant` command
5. Add `assistant` to your PATH so you can run it from anywhere
6. Launch the first-time setup wizard automatically

**You only need to run this once.** The `assistant` command will be available in every
terminal window from that point on.

---

## First-time setup

The setup wizard (`assistant init`) runs automatically at the end of installation.
You can also run it manually at any time:

```bash
assistant init
```

### What the wizard asks

**Step 1 — Platform selection**

Choose your messaging platform:
- `1` = Telegram (recommended)
- `2` = Discord
- `3` = Slack

**Step 2 — Bot token**

A token is a password that lets the runtime control your bot.
The wizard prints exact instructions for where to get it for your chosen platform.

*Telegram example:*
- Open Telegram, search for **@BotFather**
- Send `/newbot` and follow the prompts
- Copy the token it gives you (looks like `123456789:ABCdef...`)
- Paste it into the wizard

**Step 3 — Chat ID**

This tells the runtime which conversations it is allowed to respond to.
Only messages from your chat ID will get replies — everyone else is ignored.

*Telegram example:*
- Start a conversation with your new bot (send it any message)
- Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in your browser
- Look for `"chat":{"id": 123456789}` — that number is your chat ID

**Step 4 — Agent name**

An "agent" is the AI persona your assistant uses.
The default name is `main`. You can call it anything you like.

**Step 5 — Done**

The wizard writes your config, creates the agent files, and runs a health check.
If all checks pass, you are ready to start.

---

## Starting and stopping

### Start the assistant

```bash
assistant start
```

The runtime launches in the background. You can close your terminal and it keeps running.

### Stop the assistant

```bash
assistant stop
```

### Check if it is running

```bash
assistant status
```

### View the log

The runtime writes a log file. You can watch it live with:

**Mac:**
```bash
tail -f ~/Library/Logs/assistant/runtime.log
```

**Linux:**
```bash
tail -f ~/.local/state/assistant/logs/runtime.log
```

**Windows** (PowerShell):
```powershell
Get-Content "$env:LOCALAPPDATA\assistant\logs\runtime.log" -Wait -Tail 20
```

---

## Terminal commands

These are commands you type in Terminal. They manage the runtime itself.

| Command | What it does |
|---|---|
| `assistant init` | First-time setup wizard |
| `assistant configure` | Change settings (token, chat ID, model, etc.) |
| `assistant doctor` | Health check — shows what is working and what is not |
| `assistant doctor --fix` | Health check that tries to automatically fix problems it finds |
| `assistant start` | Start the runtime in the background |
| `assistant stop` | Stop the runtime |
| `assistant status` | Show whether the runtime is running |
| `assistant ui` | Open the web dashboard in your browser |
| `assistant mcp` | Start the MCP server (for connecting Claude Code directly) |
| `assistant uninstall` | Full uninstall — removes data, config, venv, PATH entry, and optionally the project directory |
| `assistant chat` | Chat with your default agent directly in the terminal |
| `assistant chat --agent <name>` | Chat with a specific agent in the terminal |
| `assistant daemon install` | Register the runtime to start automatically when you log in |
| `assistant daemon uninstall` | Remove the autostart registration |
| `assistant daemon status` | Show whether autostart is configured and active |
| `assistant manage list-agents` | List all your agents |
| `assistant manage create-agent <name>` | Create a new agent |
| `assistant manage clone-agent <name> <new-name>` | Copy an agent |
| `assistant manage rename-agent <name> <new-name>` | Rename an agent |
| `assistant manage delete-agent <name>` | Delete an agent |
| `assistant pair <code>` | Approve a new user's pairing request |
| `assistant pair --list` | Show pending pairing requests |
| `assistant completion` | Generate shell completions for bash, zsh, or fish |

---

## Chat commands

These are commands you type **inside your messaging app** (Telegram, Discord, or Slack)
in the chat with your bot. They start with a `/`.

### Status and info

| Command | What it does |
|---|---|
| `/status` | Shows which agent is active, the model being used, and runtime info |
| `/agents` | Lists all available agents |
| `/agent` | Shows details about the currently active agent |
| `/agent info <name>` | Shows details about a specific agent by name |
| `/tools` | Lists the tools the agent can use (web search, file access, etc.) |
| `/skills` | Lists installed skill plugins |

### Switching agents and settings

| Command | What it does |
|---|---|
| `/agent switch <name>` | Switch to a different agent for this conversation |
| `/model` | Shows the current Claude model being used |
| `/model <name>` | Switch to a different Claude model (e.g. `/model opus`) |
| `/effort` | Shows the current effort level |
| `/effort <level>` | Change effort level: `low`, `medium`, or `high` |
| `/session reset` | Clears the current conversation session and starts fresh |
| `/new` | Start a fresh conversation (same as `/session reset`) |
| `/reset` | Start a fresh conversation (same as `/session reset`) |
| `/compact` | Manually compact the conversation history into a summary |
| `/hooks` | Show loaded hook scripts and their events |

### Memory and notes

| Command | What it does |
|---|---|
| `/remember <text>` | Saves something to the agent's daily notes |
| `/note <text>` | Same as `/remember` |
| `/memory` | Shows memory snippets relevant to your recent messages |
| `/consolidate` | Summarizes old daily notes into long-term memory (runs automatically at night) |
| `/consolidate <days>` | Consolidate notes older than this many days |

### Search and information

| Command | What it does |
|---|---|
| `/search <query>` | Runs a web search and returns results |
| `/transcript` | Shows the last 10 messages in this conversation |
| `/transcript <n>` | Shows the last n messages |

### Tasks and reminders

| Command | What it does |
|---|---|
| `/remind <time> <message>` | Sets a reminder. Time can be `10m`, `2h`, `1d`, or a date |
| `/tasks` | Lists all your pending scheduled tasks |
| `/cancel <id>` | Cancels a task by its ID (use `/tasks` to find the ID) |

**Reminder time format examples:**
- `/remind 30m take a break` — reminds you in 30 minutes
- `/remind 2h check on the download` — reminds you in 2 hours
- `/remind 1d call the dentist` — reminds you tomorrow

### Quiet hours

Quiet hours prevent reminders from waking you up at night. Any reminder that fires during the quiet window is held back and delivered when quiet hours end instead.

| Command | What it does |
|---|---|
| `/quiet` | Shows whether quiet hours are on and what the current times are |
| `/quiet set 22:00 08:00` | Sets quiet hours from 10pm to 8am and enables them |
| `/quiet off` | Disables quiet hours |
| `/quiet on` | Re-enables quiet hours using the previously saved times |

The times use 24-hour format. Overnight windows (e.g. 22:00–08:00) work correctly. Your setting is saved to `config.json` and remembered after restarts.

### Morning briefing

The assistant can send you a proactive briefing at scheduled times each day — a warm greeting, any pending reminders, and a summary of yesterday's notes. It is off by default.

| Command | What it does |
|---|---|
| `/briefing` | Shows whether briefing is enabled and when it is scheduled |
| `/briefing now` | Generates and sends a briefing immediately |
| `/briefing on` | Enables scheduled briefings at the configured times |
| `/briefing off` | Disables scheduled briefings |
| `/briefing set <HH> [HH …]` | Sets the briefing times (replaces any existing times) |
| `/briefing add <HH>` | Adds a time to the schedule |
| `/briefing remove <HH>` | Removes a time from the schedule |

Times are in 24-hour format. You can schedule as many as you like:

```
/briefing set 9        ← just a morning briefing at 9:00
/briefing set 8 20     ← morning at 8:00 and evening at 20:00
/briefing add 13       ← add a lunchtime check-in
```

Your settings are saved to `config.json` and survive restarts.

### Obsidian (if configured)

If you have set the `OBSIDIAN_VAULT_PATH` environment variable, these commands work:

| Command | What it does |
|---|---|
| `/note read <path>` | Reads a note from your Obsidian vault |
| `/note search <query>` | Searches your vault for notes matching the query |

### Text to speech (macOS)

| Command | What it does |
|---|---|
| `/speak <text>` | Speaks the text aloud on the computer running the assistant |
| `/voices` | Lists available voices |

### Help

| Command | What it does |
|---|---|
| `/help` | Shows a quick reference of all available commands |

---

## Session compaction

As you chat with the assistant, your conversation history grows. When it gets too long,
the runtime automatically **compacts** it — older messages are summarized into a short recap,
and only the recent messages are kept in full.

This happens in the background. You do not need to do anything.

- The assistant remembers the key points from earlier in the conversation
- Recent messages are always kept in full detail
- The summary is stored in the transcript so nothing is lost

If you want to trigger compaction manually (for example, after a long coding session):

```
/compact
```

You can configure compaction behaviour in `config.json` — see [Config fields](#optional-config-fields) below.

---

## Session resets

A session reset clears the current conversation and starts fresh. The transcript is preserved
in history — you are just starting a new thread.

### Manual reset

Type any of these in chat:

```
/new
/reset
/session reset
```

### Automatic resets

You can configure the runtime to reset sessions automatically:

- **Daily reset** — reset all sessions at a specific hour each day (e.g. 4am)
- **Idle reset** — reset a session after a period of inactivity (e.g. 60 minutes)

Set these in `config.json` — see [Config fields](#optional-config-fields) below.

---

## Agent files

Each agent has its own folder inside `agents/<name>/`. These are plain text files you can
edit in any text editor to shape how your assistant behaves.

```
agents/
  main/
    AGENT.md      ← the agent's personality and rules
    USER.md       ← information about you
    MEMORY.md     ← long-term memory (grows over time)
    TOOLS.md      ← notes about tools and integrations
    memory/       ← daily notes (one file per day)
    sessions/     ← session state files
```

### AGENT.md

This is the most important file. It defines who the agent is and how it behaves.

Edit this to change the agent's personality, give it a role, set rules it must follow,
or give it background knowledge it should always have.

Example additions:
- "You are a coding assistant focused on Python."
- "Always respond in a friendly, casual tone."
- "Never give financial advice."

### USER.md

Information about you that the agent should always know.

Examples of what to put here:
- Your name and preferred name
- Your timezone and location
- Your job or area of work
- Communication preferences ("I prefer bullet points over long paragraphs")
- Any context that helps the agent serve you better

### MEMORY.md

Long-term memory. The agent reads this at the start of every conversation.

You can edit it manually, or let it grow automatically through:
- `/remember <text>` commands in chat
- The nightly memory consolidation process (which summarizes your daily notes into this file)

### TOOLS.md

Notes about tools or services the agent has access to. Mostly for your own reference
and to give the agent context about what is available.

---

## Web dashboard

The web dashboard gives you a visual overview of your runtime in a browser.

Start it with:

```bash
assistant ui
```

Then open **http://localhost:18789** in your browser.

### Dashboard tabs

| Tab | What you see |
|---|---|
| Overview | Runtime status, whether it is running, quick stats |
| Agents | All your agents and their AGENT.md content |
| Tasks | Scheduled tasks and reminders |
| Transcripts | Browse your conversation history |
| Skills | Installed skill plugins and their status |
| Chat | Chat with any agent directly in the browser |

The **Chat tab** lets you pick an agent from a dropdown, type messages, and have a full conversation without needing a Telegram or Discord account. Useful for testing agents or quick queries.

You can run the dashboard at the same time as the runtime — they do not interfere.

### Dashboard authentication

The dashboard API is protected by a bearer token, which is generated automatically during `assistant init`. The token is embedded into the dashboard page so your browser authenticates seamlessly.

If you need to regenerate the token, use `assistant configure`.

---

## Multiple agents

You can have as many agents as you want, each with a different personality or purpose.

**Common setups:**
- `main` — general personal assistant
- `builder` — focused on coding and technical work
- `research` — focused on research and writing

### Creating a new agent

```bash
assistant manage create-agent research
```

This creates the agent folder with starter files you can edit.

### Switching agents in chat

```
/agent switch research
```

The next message and all messages after it will use the `research` agent until you switch back.

### Routing a specific chat to an agent

You can permanently map a Telegram chat to a specific agent in your config file.
Use `assistant configure` or edit the config directly.

---

## DM pairing

By default, the bot only responds to chat IDs listed in your config.
**DM pairing** lets new users request access without you editing config files.

### How it works

1. A new user sends a message to your bot
2. The bot replies: "Pairing required. Your code is: **482916**"
3. You see the request in your logs, or run:
   ```bash
   assistant pair --list
   ```
4. Approve the user:
   ```bash
   assistant pair 482916
   ```
5. Their chat ID is added to your config automatically — no restart needed
6. The bot tells them they are connected

Pairing codes expire after 10 minutes and are rate-limited to one per user every 5 minutes.

To disable pairing (unknown users are silently ignored instead), set `pairing_enabled` to `false` in `config.json`.

---

## Hooks

Hooks let you run custom Python scripts when specific events happen in the runtime —
without modifying core code.

### Setting up hooks

Create `.py` files in the `hooks/` directory at the project root. They are loaded automatically when the runtime starts.

### Writing a hook

```python
# hooks/my_hook.py
from app.hooks import hook

@hook("message_in")
def on_message(event):
    print(f"Got message from {event['chat_id']}: {event['text'][:50]}")

@hook("error")
def on_error(event):
    # Send alert, log to file, etc.
    print(f"Error: {event['error']}")
```

### Available events

| Event | When it fires |
|---|---|
| `startup` | Runtime is starting up |
| `shutdown` | Runtime is shutting down |
| `message_in` | A user message was received |
| `message_out` | The assistant sent a reply |
| `session_reset` | A session was reset |
| `command` | A slash command was executed |
| `compaction` | Session compaction occurred |
| `error` | An error occurred during message handling |
| `tool_call` | A tool was invoked (web search, file access, etc.) |

Each event is a dict with at least `{"event": "...", "timestamp": "..."}` plus event-specific keys like `chat_id`, `text`, `error`, etc.

### Checking loaded hooks

Type `/hooks` in chat to see which hook scripts are loaded and what events they listen for.

An example hook file is included at `hooks/example_hook.py.disabled` — rename it to `.py` to enable it.

---

## Troubleshooting

### "assistant: command not found"

The PATH was not updated in your current terminal session.
Either open a new terminal window, or run:

```bash
source ~/.zshrc
```

### The bot is not responding

1. Check the runtime is running: `assistant status`
2. If not running, start it: `assistant start`
3. Check the log for errors: `tail -20 ~/Library/Logs/assistant/runtime.log`
4. Run a health check: `assistant doctor`

### Health check shows a failure

Run the auto-fixer first:

```bash
assistant doctor --fix
```

If it still fails, the output of `assistant doctor` will tell you exactly what is wrong
and which file or setting needs attention.

### Claude is not responding / times out

- Make sure the `claude` CLI is working: run `claude --help` in Terminal
- Make sure you are logged in: run `claude` by itself and follow any login prompts
- Check that your Anthropic account is active and has credits

### Wrong chat ID — the bot is ignoring me

- Run `assistant configure` and double-check the chat ID
- Make sure there are no extra spaces or typos
- The chat ID must be a number (example: `6390668081`), not a username

### Starting fresh

If you want to completely reset and start over:

```bash
assistant uninstall
```

The uninstall wizard walks you through removing each component:
- Runtime state, logs, and config
- Agent files (AGENT.md, MEMORY.md, daily notes)
- PATH entry from your shell profile
- The `.venv` virtual environment
- The project directory itself (e.g. `~/ClaudeClaw/assistant`) — always requires explicit confirmation
- The parent folder (e.g. `~/ClaudeClaw`) if it's empty after removal

After uninstalling, do a fresh install with:

```bash
git clone https://github.com/BrandNewBrandon/assistant-runtime.git ~/ClaudeClaw/assistant && bash ~/ClaudeClaw/assistant/install.sh
```

---

## Config file location

Your settings are stored at:

- **macOS:** `~/Library/Application Support/assistant/config/config.json`
- **Linux:** `~/.config/assistant/config.json`
- **Windows:** `%APPDATA%\assistant\config.json`

You can edit this file directly in a text editor if you prefer,
or use `assistant configure` to change settings interactively.

### Optional config fields

These fields are not required — the defaults work out of the box. Add them to `config.json` to tune behaviour.

**Rate limiting and caching**

| Field | Default | What it does |
|---|---|---|
| `cache_enabled` | `true` | Cache replies so identical messages skip Claude entirely |
| `cache_ttl_seconds` | `300` | How long (in seconds) a cached reply stays fresh |
| `cooldown_seconds_per_chat` | `1.0` | Minimum gap between Claude calls per chat |
| `max_prompt_chars` | `24000` | Hard limit on prompt size sent to Claude (~6k tokens) |

**Memory consolidation**

| Field | Default | What it does |
|---|---|---|
| `consolidation_enabled` | `true` | Run nightly consolidation automatically |
| `consolidation_hour` | `2` | Hour of day (0–23) to run consolidation |
| `consolidation_keep_days` | `3` | Consolidate notes older than this many days |

**Quiet hours**

| Field | Default | What it does |
|---|---|---|
| `quiet_hours_start` | `null` | Start of quiet window, e.g. `"22:00"` |
| `quiet_hours_end` | `null` | End of quiet window, e.g. `"08:00"` |

Quiet hours can also be set from chat with `/quiet set 22:00 08:00` — no file editing needed.

**Morning briefing**

| Field | Default | What it does |
|---|---|---|
| `briefing_enabled` | `false` | Send proactive briefings at scheduled times |
| `briefing_times` | `[9]` | List of hours (0–23) to send a briefing |

Example — morning and evening briefings:
```json
"briefing_enabled": true,
"briefing_times": [8, 20]
```

These can also be configured from chat with `/briefing on`, `/briefing set 8 20`, etc.

**Session compaction**

| Field | Default | What it does |
|---|---|---|
| `compaction_enabled` | `true` | Auto-summarize old messages when conversation gets long |
| `compaction_token_budget` | `12000` | Estimated token limit before compaction triggers |

**Session resets**

| Field | Default | What it does |
|---|---|---|
| `session_reset_daily_hour` | `null` | Hour (0–23) to auto-reset all sessions daily |
| `session_idle_reset_minutes` | `null` | Minutes of inactivity before a session auto-resets |

**Security and access**

| Field | Default | What it does |
|---|---|---|
| `dashboard_token` | (auto-generated) | Bearer token for web dashboard API access |
| `pairing_enabled` | `true` | Allow unknown users to request pairing codes |

---

## Windows notes

Everything works on Windows with a few small differences:

- Use **PowerShell** instead of Terminal for all commands
- The log file is at `%LOCALAPPDATA%\assistant\logs\runtime.log`
- The config file is at `%APPDATA%\assistant\config.json`
- Text-to-speech (`/speak`) uses the built-in Windows speech synthesizer — no extra install needed
- The `assistant` command is added to your user PATH via the Windows environment variables system,
  which takes effect in new PowerShell windows (not the one you installed from)
