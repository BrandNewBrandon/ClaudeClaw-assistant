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
- ✅ Web dashboard (`assistant ui` at localhost:18789)
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

## Phase 4 — Orchestration and sessions

### Goal
Let the system coordinate work rather than only react message-by-message.

### Includes
- background tasks
- task sessions
- resumable tasks
- concurrent jobs
- lightweight task delegation
- agent-to-agent handoff

### Exit Criteria
- the assistant can manage work across multiple flows
- background work is understandable and controllable

---

## Phase 5 — Computer and browser control

### Goal
Add practical machine-control capability.

### Includes
- browser automation
- desktop/app control
- scripted workflows
- opening apps/pages
- interacting with web UIs

### Safety Note
This phase needs a real approval and logging model.

### Exit Criteria
- the assistant can perform useful interactive tasks safely
- the system remains inspectable and controllable

---

## Phase 6 — Multi-surface assistant platform

### Goal
Expand beyond a single Telegram-first runtime.

### Possible Additions
- Discord ✅ (adapter exists)
- Slack ✅ (adapter exists)
- **iMessage** — via AppleScript + `~/Library/Messages/chat.db` polling, or BlueBubbles as a cleaner REST bridge. Requires macOS with Messages signed in. No public API; works by watching the local SQLite database and sending via `osascript`. See discussion in session notes.
- Signal
- WhatsApp — via whatsapp-web.js-style headless browser or Playwright
- richer notification channels
- calendar/email-facing workflows later

### Exit Criteria
- transport expansion does not break memory/routing/identity
- multiple surfaces feel coherent, not bolted on

---

## Phase 7 — Personal OpenClaw maturity

### Goal
Unify the system into a mature personal assistant platform.

### Includes
- reliability hardening
- richer operator introspection
- backup/export/import
- memory review tools
- cleaner permission controls
- long-term agent/config administration UX

---

## Recommended Build Order

### Right now
1. finish Phase 0 with the first real Mac validation pass
2. fix whatever the Mac pass reveals

### After that
3. finish Phase 1 polish so the assistant is solid day-to-day
4. move into Phase 2 identity realism
5. build Phase 3 tool substrate and add practical caching/usage-efficiency work at that stage
6. build Phase 4 orchestration
7. then move into Phase 5 computer/browser control

---

## Things Not To Do Too Early

- multi-bot identity before install/reliability is stable
- browser control before tool safety exists
- plugin architecture too early
- multi-surface expansion before single-surface excellence
- dashboard/UI before runtime clarity

---

## Named Milestones

### Milestone A — Installable assistant
- packageable
- configure/doctor/start/status/stop sane
- Mac validated

### Milestone B — Daily-driver assistant
- useful every day in Telegram
- memory/transcripts/agents solid

### Milestone C — Real multi-agent system
- distinct identities
- secondary bot token support
- stronger agent ownership

### Milestone D — Action-capable assistant
- tools
- shell/files/web
- useful operational actions

### Milestone E — Orchestrating assistant
- jobs
- sessions
- background work
- delegation

### Milestone F — OpenClaw-like personal platform
- browser/computer control
- richer multi-surface presence
- mature operator tooling

---

## Immediate Recommendation

Foundation, core runtime, tools, and UX polish are all in place. The assistant is daily-driver ready.

Suggested next priorities (in order):
1. **Voice memos → Whisper transcription** — Telegram voice messages piped through a local Whisper model; highest daily visibility, zero changes to the AI layer
2. **Document Q&A** — PDF attachment → text extraction → include in prompt; quick win given image handling is already wired in
3. **Semantic memory search** — config toggle wired up, embedding infrastructure exists in `app/embeddings.py` (fastembed + numpy); remaining: wire `embedding_model` config field to the embeddings module
4. **Inline Telegram approval keyboards** — replace YES/NO text replies for `run_command` with inline buttons; final UX polish

See also:
- `docs/claudeclaw-architecture.md`
