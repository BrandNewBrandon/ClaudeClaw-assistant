# Handoff Notes — Windows Setup Debugging (2026-04-07)

## Current Situation

Trying to get the assistant running on a Windows PC (`C:\Users\ace09\...`).
The bot token is valid and Telegram is receiving messages, but the assistant isn't replying.

## Root Cause

The git clone was run from `C:\Windows\System32` instead of a normal folder like
`C:\Users\ace09\Projects`. This caused the installer to save the wrong project paths
into the config file.

**Current (wrong) config paths:**
```
project_root: C:\Windows\System32\assistant-runtime
agents_dir:   C:\Windows\System32\assistant-runtime\agents
shared_dir:   C:\Windows\System32\assistant-runtime\shared
```

**What they should be:**
```
project_root: C:\Users\ace09\Projects\assistant-runtime
agents_dir:   C:\Users\ace09\Projects\assistant-runtime\agents
shared_dir:   C:\Users\ace09\Projects\assistant-runtime\shared
```

## Fix — Do This First

Run in PowerShell:

```
assistant configure
```

Enter these values when prompted (press Enter to skip everything else):
- **project_root**: `C:\Users\ace09\Projects\assistant-runtime`
- **agents_dir**: `C:\Users\ace09\Projects\assistant-runtime\agents`
- **shared_dir**: `C:\Users\ace09\Projects\assistant-runtime\shared`
- **allowed_chat_ids**: `6390668081`

Then verify and restart:

```
assistant doctor
assistant restart
```

## What "Fixed" Looks Like

`assistant doctor` should show no warnings about missing directories.
Then send a message to the Telegram bot — it should reply.

## If It Still Doesn't Reply After the Fix

Check the logs:
```
assistant logs --no-follow
```

Common things to look for:
- `404 Not Found` → bot token is wrong. Get a new one from BotFather (`/mybots`)
- `agent directory not found` → agents_dir path is still wrong
- `claude: command not found` → Claude CLI not installed or not in PATH
- `unauthorized` → chat ID not in allowed_chat_ids

## Other Known Issues on This PC

- Python 3.14 is installed (newer than tested). Should work but worth noting.
- The project is cloned at `C:\Users\ace09\Projects\assistant-runtime`
- Config file lives at: `C:\Users\ace09\AppData\Roaming\assistant\config.json`
- Log file lives at: `C:\Users\ace09\AppData\Local\assistant\logs\runtime.log`

## Claude CLI

Make sure Claude CLI is installed and authenticated:
```
claude --version
claude
```

If `claude` is not found, install it from claude.ai/code and run `claude` once to authenticate.

## Overall Project State (Mac — working fine)

- 55 tests passing
- Streaming responses working on Telegram
- Image handling working
- All CLI commands working (start, stop, restart, logs, update, restore, etc.)
- GitHub repo: https://github.com/BrandNewBrandon/assistant-runtime

## To Get These Notes on the PC

```
git pull
```

Then open `docs/handoff-2026-04-07-windows.md`.
