# Assistant Runtime Architecture

## Goal

Build a standalone personal assistant runtime that recreates the richer OpenClaw experience using:

- Claude Code subscription as the reasoning/execution engine
- Telegram as the first messaging surface
- File-based memory and state
- A clean, sustainable architecture
- Support for multiple named agents over time

This project should avoid paid model APIs and instead use the local `claude` CLI.

---

## Design Principles

1. **Workspace first**
   - Important state lives in files.
   - Files are inspectable, editable, and backup-friendly.

2. **Claude Code is the engine, not the whole system**
   - The runtime handles routing, persistence, jobs, and policy.
   - Claude handles reasoning and task execution.

3. **Deterministic runtime, flexible model behavior**
   - Scheduling, routing, logging, and permissions should be implemented in code.
   - Claude should not be responsible for core orchestration.

4. **One assistant first, many agents later**
   - Build for multi-agent support now.
   - Ship with one default agent initially.

5. **Files are source of truth**
   - Claude session resume is helpful, but not authoritative.
   - Agent memory and context should survive CLI/session failures.

6. **Simple before clever**
   - Use long-polling before webhooks.
   - Use one-shot Claude invocations before long-lived interactive sessions.
   - Use files before databases.

---

## Initial Scope

Phase 1 focuses on:

- Single Telegram bot
- Single approved user/chat
- One default agent
- Claude Code subprocess invocation
- Context loading from files
- Transcript persistence
- Daily note persistence
- Basic admin commands
- Multi-agent-ready folder structure

Not in Phase 1:

- Group chat support
- Rich tool calling
- Web UI
- Full task orchestration
- Multiple concurrent active agents in the same chat

---

## High-Level Flow

1. Telegram long-polling receives a message.
2. Router validates sender/chat.
3. Router resolves target agent.
4. Context builder loads agent files and recent context.
5. Claude runner invokes `claude --print --permission-mode bypassPermissions`.
6. Response parser extracts the user-facing reply and optional metadata.
7. Router sends reply to Telegram.
8. Persistence layer writes transcripts, logs, and daily notes.

---

## Project Layout

```text
ClaudeClaw/
  app/
    main.py
    config.py
    router.py
    telegram_client.py
    claude_runner.py
    context_builder.py
    memory.py
    sessions.py
    commands.py
    logging_utils.py
  agents/
    main/
      AGENT.md
      USER.md
      MEMORY.md
      TOOLS.md
      memory/
      sessions/
  shared/
    transcripts/
    logs/
    jobs/
    state/
    templates/
  config/
    config.example.json
  scripts/
    run.ps1
    run.sh
  README.md
  ARCHITECTURE.md
```

---

## Agent Model

Each agent lives in its own folder under `agents/<agent_name>/`.

### Agent files

- `AGENT.md`
  - Persona
  - tone
  - operating rules
  - role-specific behavior

- `USER.md`
  - who the human is to this agent
  - relationship notes
  - preferences relevant to this agent

- `MEMORY.md`
  - curated long-term memory for that agent

- `TOOLS.md`
  - local environment notes
  - preferred commands/workflows
  - machine-specific reminders

- `memory/YYYY-MM-DD.md`
  - daily notes / raw memory log

- `sessions/`
  - optional Claude session state tracking

### Why per-agent separation matters

This allows:

- multiple named agents
- clean memory boundaries
- different personalities
- task-specific agents later

---

## Runtime Components

### 1. Telegram Client
Responsibilities:
- long-polling `getUpdates`
- send messages
- send typing action
- split long messages
- track update offsets

### 2. Router
Responsibilities:
- authenticate chat/user
- detect commands vs normal messages
- map chat to agent
- serialize handling per chat
- coordinate all subsystems

### 3. Context Builder
Responsibilities:
- load agent files
- load recent transcript snippets
- load recent daily notes
- assemble Claude prompt context

### 4. Claude Runner
Responsibilities:
- invoke Claude Code subprocess
- set working directory
- manage timeout
- capture stdout/stderr
- optionally use resume/session identifiers later

### 5. Persistence Layer
Responsibilities:
- append transcript entries
- append daily memory notes
- store runtime state
- store error logs

### 6. Commands Layer
Initial commands:
- `/status`
- `/reload`
- `/session reset`
- `/agent`
- `/note ...`
- `/remember ...`

### 7. Session Manager
Responsibilities:
- track per-chat active agent
- track last activity
- optionally track Claude resume IDs
- support session reset

---

## Prompt Strategy

Phase 1 prompt composition should include:

1. runtime instructions
2. agent persona from `AGENT.md`
3. user context from `USER.md`
4. long-term memory from `MEMORY.md`
5. recent daily memory snippets
6. recent transcript turns
7. current user message
8. response formatting instructions

### Important rule

Do not rely only on Claude's internal resumed conversation state.

Use file-based context every turn so the assistant remains understandable and durable.

---

## Response Contract

Phase 1 can start simple:

- Claude returns plain reply text to send to the user.

Phase 2 should likely evolve to a structured contract, for example:

- user reply
- memory suggestion
- internal summary
- action requests

This can be markdown-delimited rather than strict JSON if needed.

---

## Memory Strategy

### Long-term memory
Stored in:
- `agents/<name>/MEMORY.md`

Use for:
- important facts
- preferences
- stable context
- lasting decisions

### Daily memory
Stored in:
- `agents/<name>/memory/YYYY-MM-DD.md`

Use for:
- conversation notes
- temporary context
- recent events
- observations worth reviewing later

### Transcripts
Stored in:
- `shared/transcripts/<surface>-<chat_id>.jsonl`

Use for:
- raw history
- debugging
- context extraction

---

## Multi-Agent Plan

### Phase 1
- one runtime
- one default agent (`main`)
- code supports agent folders
- basic `/agent` command can be stubbed or read-only

### Phase 2
- multiple named agents
- explicit per-chat active agent selection
- optional command like `/agent switch builder`

### Phase 3
- specialized agents for jobs/tasks
- delegated runs in isolated workspaces
- richer task handoff patterns

---

## Scheduling and Jobs

Phase 1:
- no heavy scheduler yet
- leave room for jobs under `shared/jobs/`

Phase 2:
- heartbeat job runner
- scheduled maintenance tasks
- reminder/event jobs

Jobs should:
- load context intentionally
- write logs
- notify only when useful

---

## Reliability Concerns

The runtime must handle:

- Telegram polling conflicts
- Claude CLI timeout
- Claude CLI auth expiration
- Claude CLI odd exit codes
- malformed Claude output
- network interruptions
- process restart recovery

### Logging
At minimum:
- router log
- claude invocation log summary
- error log
- transcript log

---

## Security Posture

- whitelist approved Telegram chat IDs
- do not expose public webhook endpoints initially
- keep bot token in config file outside repo or in ignored local config
- avoid destructive shell actions unless explicitly designed later
- do not let Claude become the permission system

---

## Phase Plan Summary

### Phase 0 — architecture
- finalize layout
- define config
- define prompt assembly
- define memory/transcript policy

### Phase 1 — usable assistant
- Telegram polling
- Claude runner
- workspace loading
- transcript persistence
- daily notes
- basic commands

### Phase 2 — stronger continuity
- structured response contract
- session tracking
- better error handling
- memory curation workflow

### Phase 3 — proactive assistant
- jobs/heartbeats
- notification policy
- quiet hours
- recurring checks

### Phase 4 — action layer
- deterministic tool execution
- action request contract
- approvals and safe automation

### Phase 5 — richer multi-agent support
- named agents
- switching
- specialized task agents

---

## Immediate Next Steps

1. Create project scaffold.
2. Add README with setup goals.
3. Create default `main` agent files.
4. Add config template.
5. Implement Phase 1 skeleton modules.
6. Start with Telegram + Claude round-trip.

---

## Naming

Project name:
- `ClaudeClaw`

The `assistant` CLI command and Python package name (`assistant-runtime`) remain unchanged.
