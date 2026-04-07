# Handoff Notes — Windows Setup + OpenClaw Parity (2026-04-07)

## Current State — Everything Working

- Bot is running on Windows (PID last seen as 19744, may change on restart)
- Telegram bot `@Avi_Nuge_Bot` (ID: 8204513759) is receiving and replying to messages
- Project is at: `C:\Users\ace09\Projects\assistant-runtime`
- Config: `C:\Users\ace09\AppData\Roaming\assistant\config.json`
- Logs: `C:\Users\ace09\AppData\Local\assistant\logs\runtime.log`
- GitHub: https://github.com/BrandNewBrandon/assistant-runtime (branch: main)
- Git identity set locally: Brandon / ace31069@msn.com

---

## What Was Fixed Today

### 1. System32 path issue
Project was cloned from `C:\Windows\System32`, so config paths pointed there.
Runtime couldn't write files (permission issues) → silent failures on every message.

**Fix applied:**
- Copied project to `C:\Users\ace09\Projects\assistant-runtime`
- Updated config paths manually
- Created missing `shared/` directory

**Fix also merged to repo (`install.ps1`):**
The installer now detects if it's being run from a system directory (`C:\Windows`,
`Program Files`, etc.) and automatically copies the project to
`C:\Users\<username>\Projects\assistant-runtime`, relaunches from there, and
prints instructions to delete the original.

### 2. Bot token was invalid
The token in config was revoked. Got a new one from BotFather.

**Current token:** `REDACTED_TOKEN`
**Token lives in:** `C:\Users\ace09\AppData\Roaming\assistant\config.json`

### 3. Claude CLI not found by subprocess (`claude_runner.py`)
On Windows, `subprocess.run(["claude", ...])` can't find `claude.cmd`.
`shutil.which("claude")` resolves correctly to the `.cmd` path.

**Fix merged:** Added `_claude_exe()` method that resolves via `shutil.which` and
uses that in both `subprocess.run` and `subprocess.Popen` calls.

### 4. `--verbose` required for stream-json
`--output-format=stream-json` with `--print` requires `--verbose` in the current
Claude CLI version. Was causing exit code 1 with no output.

**Fix merged:** Added `--verbose` to the streaming command in `claude_runner.py`.

### 5. Stale process on restart
`assistant restart` was reporting "not running" and starting a new process without
killing the old one (no PID file), so the old process kept running with the old token.

**Workaround:** `Stop-Process -Name python -Force` then `assistant start`.
The restart command itself needs a fix (not yet done — see TODO below).

---

## Personality / OpenClaw Parity Work

Compared assistant-runtime against OpenClaw's `system-prompt.ts` and made the
following changes (all merged):

### context_builder.py
- Removed bot-framing preamble ("You are operating inside a personal assistant runtime")
- Removed trailing "Reply to the user naturally" instruction
- Added instruction to *embody* AGENT.md tone (not just follow it)
- Added OpenClaw-style **Execution Bias** section:
  "If the user asks you to do work, start doing it in the same turn. Act first
  when the task is clear — do not stop at a plan or a promise to act."

### AGENT.md (default template + Avi Nuge's live file)
Rewrote from a ruleset into a personality manifesto modeled on OpenClaw's SOUL.md:
- "You're not a bot. You're a personal assistant with a point of view."
- No listing capabilities when someone says hi
- Have opinions, disagree when wrong, be direct
- Act first — don't narrate what you're about to do

---

## Commits Made Today

| Hash | Description |
|------|-------------|
| `bda96c7` | Fix Windows compatibility: installer auto-relocation + Claude CLI invocation |
| `6e7272e` | Improve default agent personality |
| `c5b7687` | Overhaul agent personality and prompt framing |

---

## Known Issues / TODO

### High priority
- **`USER.md` is empty** — Avi Nuge knows nothing about Brandon. Filling this in
  is the single highest-ROI improvement. Add: name, timezone, what you work on,
  how you like to communicate. File: `agents/Avi Nuge/USER.md`

- **Restart doesn't kill stale processes** — When there's no PID file,
  `assistant restart` starts a new process without stopping the old one.
  Needs a fix in `assistant.ps1` or the Python CLI to kill by process name
  as a fallback.

### Medium priority (OpenClaw parity)
- **Tool Call Style** — Add to `context_builder.py`: "Don't narrate routine tool
  calls, just call them. Narrate only for complex/sensitive actions."

- **Safety section** — Add to `context_builder.py`: no self-preservation, no
  power-seeking, pause if instructions conflict. (OpenClaw has this explicitly.)

- **On-demand skill loading** — Currently all skills inject context every turn.
  OpenClaw scans descriptions first, reads `SKILL.md` only when a skill clearly
  applies. Reduces noise, especially as skills grow.

- **Silent reply token** — A token like `__SILENT__` that Claude returns when no
  user-visible reply is needed (e.g., after a tool already sent the message).
  Without it, every invocation produces a reply.

### Lower priority
- **Memory retrieval quality** — Current retrieval is keyword-based. Gets less
  useful as memory grows. OpenClaw uses more semantic retrieval.

- **Heartbeat** — Proactive check-ins / daily briefings initiated by the agent.
  Scheduler exists but no heartbeat loop yet.

- **Telegram reactions** — Support emoji reactions for lightweight acknowledgements.
  Nothing in assistant-runtime supports this yet.

---

## Quick Reference

```powershell
# Start/stop/restart
& 'C:\Users\ace09\Projects\assistant-runtime\assistant.ps1' start
& 'C:\Users\ace09\Projects\assistant-runtime\assistant.ps1' stop
Stop-Process -Name python -Force; Start-Sleep -Seconds 2; & 'C:\Users\ace09\Projects\assistant-runtime\assistant.ps1' start

# Health check
& 'C:\Users\ace09\Projects\assistant-runtime\assistant.ps1' doctor

# Logs
Get-Content 'C:\Users\ace09\AppData\Local\assistant\logs\runtime.log' | Select-String '2026-04-07' | Select-Object -Last 20

# Commit and push
cd 'C:\Users\ace09\Projects\assistant-runtime'
git add <files>
git commit -m "message"
git push
```

## Troubleshooting

| Log message | Cause | Fix |
|-------------|-------|-----|
| `404 Not Found` (Telegram) | Bot token invalid | Get new token from BotFather `/mybots` → update config.json → restart |
| `Failed to execute Claude CLI` | claude.cmd not found | Should be fixed; verify `shutil.which("claude")` resolves |
| `--verbose` error | Old code | Should be fixed in current build |
| `agent directory not found` | agents_dir path wrong | Run `assistant doctor`, check config paths |
| `unauthorized` | Chat ID not in allowlist | Add to `allowed_chat_ids` in config.json |
| Bot receives messages but no reply | Stale process with old token | `Stop-Process -Name python -Force` then `assistant start` |
