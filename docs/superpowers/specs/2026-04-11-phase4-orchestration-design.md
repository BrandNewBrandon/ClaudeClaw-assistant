# Phase 4 — Orchestration and Sessions

**Date:** 2026-04-11
**Status:** Approved
**Scope:** Background tasks, job management, proactive system monitors, agent-to-agent delegation.

---

## Overview

Phase 4 moves the assistant from purely reactive (user asks → assistant answers) to orchestrated (assistant manages work across time, multiple agents, and system state). Built on the existing Scheduler/TaskStore infrastructure.

---

## Feature 1: Background Jobs

### Problem

All Claude interactions are synchronous — user sends message, waits for reply. Long-running tasks (research, code generation, analysis) block the conversation. No way to "fire and forget" a task and get notified when it's done.

### Design

#### New task type: `background_job`

Extend the scheduler to support a new task type that runs a Claude prompt in the background and delivers the result when done.

**Job lifecycle:**
1. User sends `/bg <prompt>` (or agent creates job programmatically)
2. Job created in TaskStore with `task_type="background_job"`, `status="pending"`, `fire_at=now`
3. Scheduler picks it up on next tick
4. New `_fire_background_job()` runs the prompt via `ClaudeCodeRunner.run_prompt()` in a thread
5. On completion, result delivered to the originating chat via send callback
6. On failure, error message delivered instead

**New DB table: `jobs`**

Separate from the existing `tasks` table — jobs have different lifecycle (running state, output storage, longer descriptions).

```sql
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    surface TEXT NOT NULL,
    agent TEXT NOT NULL,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, running, completed, failed, cancelled
    result TEXT,                              -- output text when done
    error TEXT,                              -- error message if failed
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
)
```

**JobStore class** — mirrors TaskStore pattern (SQLite + threading.Lock). New file: `app/job_store.py`.

**JobRunner class** — manages background execution. New file: `app/job_runner.py`.
- Maintains a thread pool (max 2 concurrent jobs to avoid overloading Claude CLI)
- Picks up pending jobs, runs them, stores results
- Delivers results via registered send callbacks (same pattern as Scheduler)

#### Commands

- `/bg <prompt>` — start a background job
- `/jobs` — list all jobs (pending, running, completed, failed)
- `/job <id>` — get job status and result
- `/job cancel <id>` — cancel a pending/running job

### What Is Not Changing

- Existing task system (reminders, scheduled messages) — unchanged
- Message handling flow — unchanged
- Tool system — background jobs don't use tools (they're simple prompt→response)

### Error Handling

- Claude timeout → job marked failed, user notified
- Claude error → job marked failed, error message stored
- Max concurrent jobs (2) exceeded → job queued as pending, picked up when slot opens

---

## Feature 2: Proactive System Monitors

### Problem

The assistant can't alert the user about system conditions (low disk space, high memory, etc.) without being asked.

### Design

#### Monitor loop

New file: `app/monitors.py` — lightweight system health checks that run on a schedule.

**MonitorRunner class:**
- Runs in a background thread (like BriefingThread)
- Polls every 5 minutes
- Checks registered monitors
- If a monitor triggers, sends alert via registered send callback
- Deduplication: don't re-alert for the same condition within a cooldown period (1 hour default)

**Built-in monitors:**

1. **Disk usage** — alert if any monitored path exceeds threshold (default 90%)
2. **Process count** — alert if total process count is unusually high (>500)

Each monitor is a simple function: `() -> str | None`. Returns alert message or None.

#### Configuration

No new config fields — monitors are always-on with sensible defaults. Can be disabled via `/monitors off` command if needed.

#### Commands

- `/monitors` — show active monitors and their status
- `/monitors on` / `/monitors off` — enable/disable

### What Is Not Changing

- Existing tools (disk_usage, list_processes) — unchanged, monitors reuse same underlying calls
- Scheduler — monitors are independent (own thread, own loop)

---

## Feature 3: Agent-to-Agent Delegation

### Problem

No way for a user (or agent) to hand off a task from one agent to another. Must manually switch agents.

### Design

#### `/delegate <agent> <prompt>` command

Send a prompt to a different agent, get the response back in the current chat. The delegated agent runs the prompt using its own context (AGENT.md, memory, etc.) but the result is delivered to the requesting chat.

**Implementation:**
- CommandHandler receives the `/delegate` command
- Creates a background job (reusing Feature 1 infrastructure) with the target agent
- Job runs using the target agent's context
- Result delivered to originating chat, prefixed with `[{agent_name}]:` 

This is intentionally simple — no persistent agent-to-agent sessions, no bidirectional communication. Just "ask another agent for help and get the answer back."

### What Is Not Changing

- Agent isolation — each agent still has its own memory, personality
- Active agent — doesn't change when delegating

---

## Files Touched Summary

| File | Change |
|------|--------|
| `app/job_store.py` | New — JobStore (SQLite) |
| `app/job_runner.py` | New — JobRunner (background execution + delivery) |
| `app/monitors.py` | New — MonitorRunner + built-in monitors |
| `app/commands.py` | Add `/bg`, `/jobs`, `/job`, `/delegate`, `/monitors` commands |
| `app/router.py` | Initialize JobRunner + MonitorRunner, register senders |
| `tests/test_job_store.py` | New — JobStore tests |
| `tests/test_job_runner.py` | New — JobRunner tests |
| `tests/test_monitors.py` | New — monitor tests |
| `tests/test_commands.py` | New tests for new commands |

## Testing Strategy

- Unit test JobStore CRUD operations
- Unit test MonitorRunner with mock monitors
- Unit test commands in isolation
- Integration: JobRunner with mock model runner
- All existing tests must continue passing
