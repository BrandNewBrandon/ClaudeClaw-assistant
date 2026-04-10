# Phase 2 — Agent Identity Separation

**Date:** 2026-04-10  
**Status:** Approved  
**Scope:** Make ClaudeClaw agents feel like genuinely distinct entities with separate tokens, session history, and conversation memory.

---

## Problem

The multi-account infrastructure exists in config, but three gaps prevent agents from being truly isolated:

1. **Session bleed** — `_session_ids` is keyed by `surface:account:chat_id`. Switching agents in a chat hands the new agent the old Claude session ID, so `builder` inherits `main`'s conversation context.
2. **Transcript bleed** — `append_transcript` and `read_recent_transcript` are not scoped by agent. Both bots read from the same recent history when building context for a reply.
3. **No second bot token in use** — The `accounts` config dict supports multiple tokens but has never been exercised for a second Telegram bot. The routing and polling paths need validation end-to-end.

---

## Goal

Each bot has:
- Its own Telegram token and visible identity (username, avatar)
- Its own Claude session — no context inherited from another agent
- Its own transcript history — each agent reads only its own recent conversations
- Its own personality via `AGENT.md` (already working, no changes needed)
- Its own memory notes under `agents/<name>/memory/` (already working, no changes needed)

---

## Design

### 1. Session isolation

**File:** `app/router.py`, `app/chat_session.py`

Change `_session_key()` to include `agent_name`:

```
Before: f"{surface}:{account_id}:{chat_id}"
After:  f"{surface}:{account_id}:{chat_id}:{agent_name}"
```

This key is used as the lookup into `_session_ids` (the dict mapping → Claude `--resume` session ID). With agent included, switching agents starts a fresh Claude conversation rather than resuming the previous one.

`SessionStore` (which persists the *active* agent across restarts) is unaffected — it already uses this key correctly.

In `chat_session.py`, `_session_ids` is a plain dict using `self._chat_id` as the key. Update to include `self._agent_name` so the terminal REPL has the same isolation guarantee.

### 2. Transcript isolation

**File:** `app/memory.py`, all call sites in `router.py`, `chat_session.py`, `mcp_server.py`

Add `agent_name: str` as a parameter to:
- `MemoryStore.append_transcript()`
- `MemoryStore.read_recent_transcript()`

The agent name is used to namespace the transcript key so each agent writes to and reads from its own slice of history. A conversation with `main` is never visible to `builder` when it builds its context.

Daily notes are already per-agent (`agents/<name>/memory/YYYY-MM-DD.md`). No changes needed there.

### 3. Multi-account config — second bot token

**File:** `app/config.py`, `config/config.example.json`, `GUIDE.md`

The target config shape for two dedicated bots:

```json
"accounts": {
  "primary": {
    "platform": "telegram",
    "token": "<main-bot-token>",
    "allowed_chat_ids": ["<your-chat-id>"]
  },
  "builder": {
    "platform": "telegram",
    "token": "<builder-bot-token>",
    "allowed_chat_ids": ["<your-chat-id>"]
  }
},
"routing": {
  "primary": { "default_agent": "main" },
  "builder": { "default_agent": "builder" }
}
```

Each account gets its own polling thread and routes exclusively to its dedicated agent. No `chat_agent_map` needed — the account *is* the identity.

Work:
- Validate this config shape works through startup, polling, and reply path
- Fix any rough edges in the router's multi-account initialization
- Update `config.example.json` to show the two-bot pattern
- Add a "Multiple bots" section to `GUIDE.md`

---

## What Is Not Changing

- `AGENT.md` loading — already per-agent, no bleed
- Daily notes and long-term `MEMORY.md` — already under `agents/<name>/`, no bleed
- `chat_agent_map` — still supported for accounts that want it; dedicated accounts just don't use it
- Hook system, tool loop, scheduler, briefing — unaffected
- Dashboard — already reads `active_agent` per account from `RuntimeState`

---

## Testing

| Test | What it verifies |
|------|-----------------|
| Session key includes agent | Two agents in same chat produce different keys; switching agent produces new key |
| No session ID bleed on agent switch | After switch, `prior_session_id` is `None` for the new agent |
| Transcript scoped by agent | `append_transcript` for agent A is invisible to `read_recent_transcript` for agent B |
| Multi-account config loads | Two-token config parses correctly, both accounts boot, each routes to its agent |
| Existing tests still pass | All 79 current tests unmodified or updated for new signatures |

---

## Files Touched

| File | Change |
|------|--------|
| `app/router.py` | `_session_key()` includes agent; transcript calls pass agent |
| `app/chat_session.py` | Session key includes agent; transcript calls pass agent |
| `app/memory.py` | `append_transcript` + `read_recent_transcript` accept agent param |
| `app/mcp_server.py` | Update transcript call sites |
| `config/config.example.json` | Show two-bot pattern |
| `GUIDE.md` | Add "Multiple bots" section |
| `tests/` | New + updated tests for session isolation, transcript isolation, multi-account config |
