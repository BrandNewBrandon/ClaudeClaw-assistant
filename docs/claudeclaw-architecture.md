# ClaudeClaw Architecture Plan

## Purpose

ClaudeClaw is the working concept for turning `assistant-runtime` into a personal OpenClaw-like assistant platform powered by Claude Code.

The design goal is **not** to copy OpenClaw mechanically. The goal is to reproduce the important capabilities and operating model:
- persistent identity
- memory and continuity
- multi-agent / multi-account presence
- structured tools
- background jobs and orchestration
- strong operator visibility
- eventual browser/computer control

while using **Claude Code** as the primary reasoning and coding engine.

---

## Core Principle

Treat:
- **Claude Code** as the brain / worker
- **ClaudeClaw** as the runtime / transport / memory / tool / orchestration platform

Claude Code should not become the whole system. ClaudeClaw should own the platform concerns:
- transport normalization
- routing and identity
- memory persistence and retrieval
- tool execution
- approvals and safety boundaries
- task orchestration
- logs and operator introspection

---

## Capability Layers

### 1. Transport Layer
Handles external surfaces such as Telegram first, later Discord/Signal/Slack.

Responsibilities:
- receive messages/events
- normalize them into one internal event structure
- send replies back to the correct surface/account
- keep transport identity separate from agent identity

Current status:
- Telegram transport exists
- multiple Telegram accounts now work through one runtime

Next direction:
- clean transport abstraction
- per-surface adapters
- better normalized event metadata

### 2. Identity and Routing Layer
Determines which agent is responding and why.

Key concepts:
- accounts = external bot identities
- agents = internal personas/operators
- routing = account-local chat-to-agent mapping
- sessions = active per-chat/per-account state

Responsibilities:
- pinned routing
- session-based switching
- account-aware session ownership
- later, per-agent permissions and policies

Current status:
- agents exist
- routing exists
- multi-account session scoping exists

Next direction:
- stronger per-agent boundaries
- clearer session ownership
- better task ownership by agent

### 3. Memory Layer
Provides continuity instead of raw transcript-only behavior.

Memory types:
- transcripts
- daily notes
- long-term memory
- task memory
- per-agent memory where useful

Responsibilities:
- append raw transcripts
- distill important information
- retrieve relevant memory snippets
- keep context sizes practical
- separate durable memory from noisy logs

Current status:
- transcripts and daily notes exist

Next direction:
- add long-term memory store
- add retrieval/search
- add memory maintenance and distillation flows
- add explicit remember/review behavior

### 4. Tool Substrate
Lets the system act in structured, inspectable ways.

Tool families:
- file read/write/edit
- shell execution
- process management
- web fetch/search
- diagnostics
- later browser/computer tools

Responsibilities:
- register tools cleanly
- expose tool capabilities to the reasoning layer
- execute tools safely
- log tool usage
- add approval gates where needed

Current status:
- not yet implemented as a first-class runtime layer

Next direction:
- start with file + shell + process + web tools

### 5. Claude Worker Layer
Uses Claude Code for reasoning, coding, and higher-order task execution.

Responsibilities:
- solve reasoning-heavy tasks
- perform coding work
- interpret context and tool results
- eventually participate in delegated subtask execution

Design rule:
- Claude Code is the worker, not the whole runtime

Current status:
- Claude Code already powers response generation

Next direction:
- improve prompt assembly
- integrate structured tools
- support longer-lived task execution modes

### 6. Orchestration Layer
Lets ClaudeClaw manage work over time.

Concepts:
- tasks
- background jobs
- resumable work
- progress updates
- delegation
- agent-to-agent handoff

Responsibilities:
- start, monitor, resume, cancel, summarize tasks
- keep task state inspectable
- allow chat-triggered work to continue beyond one reply

Current status:
- largely missing

Next direction:
- add task records
- add background execution model
- add job status inspection and follow-up

### 7. Operator Layer
Makes the system understandable and trustworthy to run.

Responsibilities:
- doctor/status/inspect
- logs and runtime state
- per-account/per-agent visibility
- failure diagnosis
- latency visibility
- config validation and migration support

Current status:
- configure/doctor/status/start/stop exist
- logs/pid/lock handling exists
- doctor now understands multiple accounts

Next direction:
- per-account latency/health details
- task inspection
- tool audit trail
- better operational summaries

---

## Internal Event Flow

Target message flow:
1. Transport receives event
2. Event is normalized into internal message structure
3. Identity/routing resolves responding agent
4. Context loader gathers agent context + memory + session state
5. Runtime decides execution mode
   - runtime-native command
   - tool-driven action
   - Claude response
   - background task
6. Claude worker and/or tools execute
7. Memory/task/log state is persisted
8. Reply/update is sent to the source transport

This separation keeps ClaudeClaw inspectable and prevents Claude Code from becoming an opaque god-process.

---

## What Maps Cleanly From OpenClaw

OpenClaw-like concepts that map well:
- surfaces/accounts
- sessions
- long-term and daily memory
- structured tools
- background tasks
- sub-agent/delegation patterns
- operator introspection

---

## What Must Be Different

Because Claude Code is the engine:

1. **Not every interaction should require a heavyweight Claude run**
   - `/status`, routing commands, and many runtime inspections should stay native

2. **Tool execution should remain owned by ClaudeClaw**
   - the runtime should control permissions, execution, and logging

3. **Coding tasks are a native strength**
   - ClaudeClaw should lean into file/repo/task execution as a first-class advantage

---

## Build Plan

### Phase 1 — Runtime polish
- parallel per-account polling
- latency instrumentation
- runtime lifecycle cleanup
- improved status visibility

### Phase 2 — Real memory
- long-term memory store
- memory retrieval/search
- daily-note distillation
- remember/review flows

### Phase 3 — Tool substrate
- file tools
- shell tools
- process tools
- web tools
- safety/approval model where needed

### Phase 4 — Orchestration
- task model
- background jobs
- resumable work
- progress reporting
- delegated Claude work

### Phase 5 — Agent realism
- stronger per-agent boundaries
- per-agent memory shaping
- per-agent permissions/policies
- clearer task ownership

### Phase 6 — Browser/computer control
- browser automation
- desktop/app control
- approval and audit model

### Phase 7 — Multi-surface expansion
- additional transports beyond Telegram
- unified routing/memory across surfaces

---

## Immediate Priorities

Recommended next implementation order:
1. parallel per-account polling
2. latency instrumentation
3. long-term memory + retrieval
4. file/shell/web tools
5. background task/session model

---

## Success Criteria

ClaudeClaw will feel real when it can:
- respond through multiple accounts/surfaces cleanly
- remember useful prior context
- use structured tools to inspect and act
- manage background work over time
- keep agent identities distinct
- explain what it is doing and why
- remain operator-visible and debuggable

That would constitute a real personal OpenClaw-like platform powered by Claude Code.
