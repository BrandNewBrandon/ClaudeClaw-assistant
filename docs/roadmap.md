# Roadmap

## North Star

Build a personal assistant system that recreates the parts of the OpenClaw experience that matter most, but powered by Claude Code instead of paid API-first model infrastructure.

Target qualities:
- persistent assistant identity
- chat-native interaction
- agent personas
- memory and continuity
- operator tooling
- installable local runtime
- controllable local actions
- eventual browser/computer/tool orchestration

---

## Design Principles

### 1. Local-first and inspectable
Prefer:
- file-based config
- file-based logs
- readable state
- understandable behavior

### 2. Capability layers, not chaos
Add one major capability layer at a time.
Avoid stacking browser control, multi-bot identity, orchestration, and platform expansion all at once.

### 3. Claude Code is the brain, not the whole platform
Claude Code handles reasoning and coding strength.
The runtime, transport, memory, tooling, and orchestration still need to be built around it.

### 4. Operator trust matters
The system should make it easy to answer:
- what is running?
- where are logs?
- where is config?
- which agent is active?
- why did something fail?

### 5. Identity should become real over time
If agents are going to feel distinct, they eventually need stronger routing, behavior, and possibly distinct external identities.

---

## Completed

### Foundation
- ✅ Package/import cleanup and `assistant` command surface
- ✅ Config and runtime path centralization
- ✅ Doctor / configure / lifecycle commands (start / stop / status)
- ✅ Log / PID / lock handling
- ✅ Mac and Windows validation
- ✅ Cross-platform install scripts (`install.sh`, `install.ps1`)
- ✅ **Double-clickable installers** — `Mac Install.command` (Finder) and `Windows Install.bat` (File Explorer)

### Assistant runtime
- ✅ Stable Telegram polling and replies
- ✅ Transcript persistence and daily notes
- ✅ Agent switching, routing, and per-agent config
- ✅ Multi-account support (Telegram, Discord, Slack channel adapters)
- ✅ Web dashboard (`assistant dashboard` at localhost:18790)
- ✅ MCP server (`assistant mcp`)
- ✅ Terminal REPL (`assistant chat`)
- ✅ Daemon autostart (`assistant daemon install`)

### Tools and skills
- ✅ Tool loop (web_search, web_fetch, read_file, write_file, list_dir, run_command)
- ✅ Local system tools (disk_usage, list_processes) — approval-free read-only queries
- ✅ Dev/coding agent (builder) — safe_commands whitelist, working_dir override, execution-biased persona
- ✅ Plugin / skill system (GitHub, Obsidian, TTS, Browser skills)
- ✅ Slash command surface (/remind, /tasks, /quiet, /memory, /consolidate, etc.)
- ✅ Response caching and cooldown tracking
- ✅ SQLite-backed task scheduler with quiet hours
- ✅ Nightly memory consolidation thread
- ✅ Context assembly caching — mtime-based file cache in ContextBuilder eliminates redundant disk reads

### UX and polish
- ✅ **Streaming responses** — live token-by-token editing in Telegram with tool status indicators
- ✅ **Image / photo handling** — Telegram photos passed to Claude via temp file path
- ✅ **Morning briefing** — configurable proactive daily digest (`/briefing`, `briefing_times` config)
- ✅ Session continuity via `--resume` session IDs

---

## Phase 0 — Foundation stabilization

### Goal
Make the runtime installable, understandable, and cross-platform enough to support future growth.

### Includes
- package/import cleanup
- `assistant` command surface
- config path centralization
- runtime path centralization
- doctor/configure polish
- lifecycle commands
- log/pid/lock handling
- docs cleanup
- first real Mac validation

### Exit Criteria
- install works on Windows and Mac
- configure works
- doctor works
- start/status/stop are sane enough
- logs are easy to find
- no major repo-root surprises remain

---

## Phase 1 — Core OpenClaw-like assistant runtime

### Goal
Recreate the core assistant-presence layer.

### Includes
- stable Telegram-based assistant behavior
- transcript persistence
- daily notes / memory continuity
- agent switching and routing
- per-agent config and personality shaping
- trustworthy operator commands

### Exit Criteria
- day-to-day use feels natural
- switching agents is reliable
- memory/transcript behavior is useful
- operational debugging is straightforward

---

## Phase 2 — Identity and multi-agent realism

### Goal
Make agents feel like real distinct entities, not just config presets.

### Includes
- stronger per-agent behavior separation
- better agent lifecycle tooling
- clearer session ownership/routing
- per-agent transcript/memory distinctions where useful
- eventually: multiple bot tokens / multiple visible bot identities

### Important Note
This is where secondary bot token support belongs.

### Exit Criteria
- agents feel operationally distinct
- external identity separation is possible where useful
- switching among agents does not feel fake or fragile

---

## Phase 3 — Tool substrate and efficiency ✅ COMPLETE

### Goal
Give the assistant structured action-taking abilities while improving usage efficiency.

### Phase 3A — Local action tools ✅
- file reads/writes
- shell execution
- process control
- safe command wrappers

### Phase 3B — Web and information tools ✅
- web fetch/search
- page extraction
- image support later if useful

### Phase 3C — Local system tools ✅
- disk_usage — total/used/free for any filesystem path
- list_processes — running processes with optional name filter
- (service checks left to run_command — appropriate to gate behind approval)

### Phase 3D — Caching and usage efficiency ✅
- context assembly caching — mtime-based _read_cached in ContextBuilder
- (transcript-window optimization and model-output caching deferred)

### Exit Criteria ✅
- the assistant can do more than chat and reason
- tools feel reusable and inspectable
- repeated operations waste less usage and time

---

## Phase 3.5 — Practical daily-driver features ✅ COMPLETE

### Goal
Add high-value features that don't require architectural changes — incremental wins before the orchestration leap.

### Delivered
- ✅ **Scheduled messages / reminders** — `/remind` command with time-spec parsing, SQLite persistence, quiet hours deferral
- ✅ **Message forwarding across surfaces** — `/forward` command with cross-surface targeting via scheduler send callbacks
- ✅ **Conversation export / search** — `/search-chat` (substring search), `/export` (formatted text export)
- ✅ **PDF document Q&A** — drop PDF into Telegram, text extracted via pymupdf, inlined (≤5 pages) or saved to file

---

## Phase 4 — Orchestration and sessions ✅ COMPLETE

### Goal
Let the system coordinate work rather than only react message-by-message.

### Delivered
- ✅ **Background jobs** — `/bg` command, JobStore (SQLite), JobRunner (threaded, max 2 concurrent), full tool loop + conversation context
- ✅ **Agent delegation** — `/delegate <agent> <prompt>` runs prompt with target agent's context
- ✅ **Job management** — `/jobs`, `/job <id>`, `/job cancel <id>`
- ✅ **Proactive system monitors** — MonitorRunner with disk usage + process count checks, configurable cooldown
- ✅ **Stale job recovery** — orphaned running jobs marked failed on startup

---

## Phase 5 — Computer and browser control ✅ COMPLETE

### Goal
Add practical machine-control capability.

### Delivered
- ✅ **10 cross-platform tools** — screenshot, mouse_click, mouse_move, keyboard_type, keyboard_hotkey, scroll, open_url, open_app, get_screen_size, get_mouse_position
- ✅ **Opt-in per agent** — `"computer_use": true` in agent.json
- ✅ **Approval gate** — action tools require user approval via inline buttons; `"computer_use_auto_approve": true` to skip
- ✅ **Tool loop limit raised** — 10 iterations for computer use agents (vs 3 default)
- ✅ **Cross-platform** — pyautogui works on macOS, Windows, Linux

---

## Phase 6 — Multi-surface assistant platform ✅ COMPLETE

### Goal
Expand beyond a single Telegram-first runtime.

### Delivered
- ✅ Discord adapter (event-driven, discord.py)
- ✅ Slack adapter (Socket Mode, slack-sdk)
- ✅ **iMessage adapter** — polls ~/Library/Messages/chat.db, sends via AppleScript. macOS only. No external dependencies.
- ✅ **WhatsApp adapter** — HTTP bridge pattern, protocol-agnostic. Works with any bridge server (whatsapp-web.js, Baileys, whatsmeow).
- ✅ **Setup wizard** — `assistant init` and `assistant configure` support all 5 platforms with tailored prompts
- ✅ **Doctor checks** — platform-specific health validation (iMessage DB, WhatsApp bridge connectivity)

---

## Phase 7 — Personal OpenClaw maturity ✅ COMPLETE

### Goal
Unify the system into a mature personal assistant platform.

### Delivered
- ✅ **Backup/restore** — `assistant backup` / `assistant backup-restore` with manifest, dry-run, skip lock files
- ✅ **Transcript rotation** — auto-archive at 5000 lines, keep 2000 recent, safe archive-before-truncate
- ✅ **Thread health tracking** — message/tool/error counters in RuntimeState
- ✅ **`/diagnostics` command** — runtime metrics, thread health, error counts
- ✅ **Reliability hardening** — SQLite timeouts, file write locks, config permissions (0o600), startup validation, config field range checks, polling failure tracking with escalation
- ✅ **Token masking utility** — mask_token() for safe display of secrets

---

## Milestones — All Complete

| Milestone | Status | Description |
|-----------|--------|-------------|
| A — Installable assistant | ✅ | Packaged, cross-platform, doctor/configure/start/stop |
| B — Daily-driver assistant | ✅ | Telegram, memory, transcripts, agents, streaming |
| C — Real multi-agent system | ✅ | Distinct identities, multi-bot tokens, session isolation |
| D — Action-capable assistant | ✅ | Tools, shell, files, web, PDF, approval gates |
| E — Orchestrating assistant | ✅ | Background jobs, delegation, monitors, scheduling |
| F — Personal platform | ✅ | Computer use, 5-surface support, backup/restore, diagnostics |

---

## Current State (April 2026)

All phases 0–7 are complete. 231 tests passing. The system is:
- Feature-complete across messaging, tools, orchestration, and computer control
- Cross-platform (macOS, Windows, Linux)
- Multi-surface (Telegram, Discord, Slack, iMessage, WhatsApp)
- Reliability-hardened (file locks, SQLite timeouts, config validation, polling resilience)
- Documented (GUIDE.md, setup wizard, doctor checks)
- Backed up (assistant backup/restore)

## Future Possibilities

- Signal adapter
- Calendar/email integration
- Richer dashboard visualizations
- Plugin marketplace
- Mobile companion app

See also:
- `docs/claudeclaw-architecture.md`
