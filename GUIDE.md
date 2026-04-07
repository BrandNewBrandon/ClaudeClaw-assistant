# assistant-runtime — User Guide

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
8. [Agent files](#agent-files)
9. [Web dashboard](#web-dashboard)
10. [Multiple agents](#multiple-agents)
11. [Troubleshooting](#troubleshooting)

---

## What it is

assistant-runtime is a background program that:

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

### macOS

Double-click **`Mac Install.command`** in Finder.

macOS will ask if you want to open it — click **Open**. A Terminal window appears and runs the installer automatically.

### Windows

Double-click **`Windows Install.bat`** in File Explorer.

A PowerShell window opens and runs the installer automatically. No extra configuration needed.

### Prefer the terminal?

**Mac / Linux:**
```bash
cd ~/Projects/assistant-runtime
bash install.sh
```

**Windows (PowerShell):**
```powershell
cd ~\Projects\assistant-runtime
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
| `assistant uninstall` | Remove all runtime data and config |
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
assistant stop
assistant uninstall
bash install.sh
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

---

## Windows notes

Everything works on Windows with a few small differences:

- Use **PowerShell** instead of Terminal for all commands
- The log file is at `%LOCALAPPDATA%\assistant\logs\runtime.log`
- The config file is at `%APPDATA%\assistant\config.json`
- Text-to-speech (`/speak`) uses the built-in Windows speech synthesizer — no extra install needed
- The `assistant` command is added to your user PATH via the Windows environment variables system,
  which takes effect in new PowerShell windows (not the one you installed from)
