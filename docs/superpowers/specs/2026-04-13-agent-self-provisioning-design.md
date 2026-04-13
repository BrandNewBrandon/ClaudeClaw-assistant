# Agent Self-Provisioning — Design

**Date:** 2026-04-13
**Status:** Draft, pending review
**Scope:** Let running agents create new agents on user request, scaffold their config/persona files, and bind per-channel credentials (Telegram, Discord, Slack, iMessage) — each new agent gets its own identity on every channel, hot-loaded into the running process without a restart.

---

## Goals

1. User says *"spin up a finance agent with all channels"*; the current agent performs the entire provisioning flow from inside the conversation.
2. Each new agent has its own Telegram bot, Discord bot, Slack app, and iMessage group-chat routing — no token reuse.
3. New agents inherit knowledge of how to spawn further agents (they're created from a template that documents it).
4. Tokens never live in plaintext `config.json`; they live in the OS secret store via `keyring` (macOS Keychain / Windows Credential Manager), cross-platform.
5. Mac and Windows both work. No hard-coded platform paths.

## Non-goals

- WhatsApp provisioning (ToS / Meta Business friction too high — manual wiring only, excluded from `create_agent` flow).
- Per-agent Apple IDs (iMessage uses single shared Apple ID, routes by `chat_identifier`).
- Automated Telegram/Discord/Slack account creation (impossible — all three require interactive human steps at `@BotFather` / developer portal / app manifest UI).
- Multi-user credential isolation (single-user runtime; no per-user keychains).

---

## Architecture

Four new pieces, each isolated and independently testable.

### 1. `SecretStore` (`app/secret_store.py`)

Thin wrapper around `keyring`. Single responsibility: store and retrieve tokens keyed by `(agent_name, channel)`.

**Interface:**
```python
class SecretStore:
    SERVICE = "claudeclaw"

    def set(self, agent: str, channel: str, token: str) -> None: ...
    def get(self, agent: str, channel: str) -> str | None: ...
    def delete(self, agent: str, channel: str) -> None: ...
    def list_bindings(self) -> list[tuple[str, str]]: ...  # (agent, channel)
```

Username format: `{agent}:{channel}` (e.g. `finance:telegram`). Service: `claudeclaw`.

**Migration:** On runtime startup, scan `config.json` for any `accounts[*].token` still in plaintext. Move each to the keyring, replace with `token_ref: "{agent}:{channel}"`, rewrite `config.json`. Idempotent — skips already-migrated accounts.

**Dependency:** `keyring>=24` added to `pyproject.toml` base deps (not optional — required for security).

### 2. Hot config reload in `AssistantRouter` (`app/router.py`)

Current state: `run()` reads config once, spawns one polling thread per account, never re-reads. Adding a new account requires a restart.

**Change:** Add `router.add_account(account_id: str)` method.

1. Reload `config.json` from disk.
2. Look up the new `AccountConfig`.
3. Resolve token via `SecretStore` if `token_ref` is set.
4. If the channel is event-driven (Discord/Slack), call the existing `_start_event_driven_channels` logic for that one account.
5. If polling (Telegram), spawn a new `threading.Thread` target at `self._account_worker` and register it in `self._active_workers`.
6. Return success/failure status.

Also add `router.remove_account(account_id)` for symmetry (used on unbind / agent deletion later — not in v1 implementation but reserved in the interface).

**Thread safety:** guarded by a new `self._accounts_lock = threading.Lock()`. `add_account` takes the lock for the duration of the spawn. Existing workers don't touch the lock.

### 3. Provisioning tools (`app/tools.py`)

Three new tools registered in `build_default_registry()`:

#### `create_agent(name, persona, description?)`
- Validates `name` (lowercase alnum + dash, not already present).
- Copies `agents/_template/` to `agents/{name}/`.
- Renders `agent.json`, `AGENT.md`, `TOOLS.md` by substituting `{{name}}`, `{{persona}}`, `{{description}}`.
- Default `agent.json`: `model: "opus"`, `effort: "high"`, `safe_commands: []`, `working_dir: null`, all tools enabled.
- Returns: next-steps text pointing at `bind_channel`.
- **Gated** behind YES/NO approval.

#### `bind_channel(agent, channel, **kwargs)`
Dispatches by `channel`:

- **`telegram`**: requires `token`. Validates by calling Telegram `getMe`. Stores token in `SecretStore`. Appends account to `config.json` with `token_ref`. Calls `router.add_account()`. Triggers the existing pairing flow (new bot DMs user for 6-digit code).
- **`discord`**: requires `token`. Validates by calling Discord `/users/@me`. Same store/config/reload pattern.
- **`slack`**: requires `bot_token` + `app_token`. Validates both. Same pattern.
- **`imessage`**: requires `chat_identifier` (the Messages.app group/thread id). No token. Appends routing rule to config, reloads router. Uses helper `list_imessage_chats()` to show recent chats so user can pick by name instead of copy-pasting an id.

Returns success message with a "try DMing the new bot" hint.
**Gated** behind YES/NO approval (bot tokens are maximally privileged).

#### `list_imessage_chats(limit=20)`
- Reads Messages.app sqlite (`~/Library/Messages/chat.db`) to list recent group chats with their `chat_identifier`s.
- **macOS only** — returns a clear error on Windows ("iMessage requires macOS; bind this channel from your Mac").
- Not gated (read-only, local).

### 4. Agent template (`agents/_template/`)

New directory with three files:

- **`agent.json`** — placeholders for name/persona/etc
- **`AGENT.md`** — persona + a **"Spawning Sub-Agents"** section that documents `create_agent` and `bind_channel` inline, so every agent spawned from the template knows how to spawn further agents
- **`TOOLS.md`** — standard tool list, same as existing agents

The template's `AGENT.md` "Spawning Sub-Agents" section is also appended to `agents/main/AGENT.md` and `agents/builder/AGENT.md` in this same change, so existing agents inherit the capability.

---

## Per-channel provisioning UX

Each `bind_channel` invocation walks the user through the interactive step. The agent prints copy-paste-ready instructions as the first tool result, waits for the user to reply with the token(s), then calls `bind_channel` again with the token filled in.

### Telegram
```
1. Open @BotFather in Telegram
2. Send: /newbot
3. Name: {AgentName} Assistant
4. Username: yourname_{agent}_bot
5. Paste the token back here
```

### Discord
```
1. Go to https://discord.com/developers/applications
2. New Application → name it "{AgentName} Assistant"
3. Left sidebar → Bot → Add Bot → Copy token
4. Left sidebar → OAuth2 → URL Generator → scopes: bot, applications.commands → permissions: Send Messages, Read Message History → copy URL, open, add to your server
5. Paste the bot token back here
```

### Slack
The agent emits a full app manifest YAML (name, scopes, events, socket mode enabled) as part of the instructions so the user just pastes it into `api.slack.com/apps → Create from manifest`. Then:
```
1. Install to workspace
2. OAuth & Permissions → copy Bot User OAuth Token
3. Basic Information → App-Level Tokens → Generate → scope connections:write → copy token
4. Paste both tokens back here (bot_token=..., app_token=...)
```

### iMessage
```
1. Open Messages.app
2. Create a new conversation with yourself (or a group chat named "{agent}")
3. Send one message so the chat exists in the database
4. I'll list your recent chats — pick one.
[agent runs list_imessage_chats() and shows a numbered list]
```
User replies with a number; agent calls `bind_channel(channel="imessage", chat_identifier=...)`.

---

## Data flow

```
User → "spin up finance agent with all channels"
  ↓
Agent calls create_agent(name="finance", persona="…")
  → scaffolds agents/finance/, returns next-steps
  ↓
Agent: "Which channels? (telegram/discord/slack/imessage/all)"
User: "all"
  ↓
Agent prints Telegram BotFather steps → user pastes token
Agent calls bind_channel(agent="finance", channel="telegram", token=…)
  → SecretStore.set("finance", "telegram", token)
  → config.json updated with token_ref
  → router.add_account("finance-telegram")
  → new polling thread live, new bot DMs user for pairing
  ↓
[repeat for discord, slack, imessage]
  ↓
Agent: "finance is live on 4 channels."
```

---

## Config schema change

**Before:**
```json
{"accounts": {"primary": {"token": "123:abc", "channel": "telegram", "agent": "main"}}}
```

**After:**
```json
{"accounts": {
  "primary":          {"token_ref": "main:telegram",    "channel": "telegram", "agent": "main"},
  "finance-telegram": {"token_ref": "finance:telegram", "channel": "telegram", "agent": "finance"},
  "finance-discord":  {"token_ref": "finance:discord",  "channel": "discord",  "agent": "finance"},
  "finance-slack":    {"token_ref": "finance:slack",    "channel": "slack",    "agent": "finance"},
  "finance-imessage": {"chat_identifier": "chat123",    "channel": "imessage", "agent": "finance"}
}}
```

`AccountConfig` gains optional `token_ref: str | None` field. Loader resolves it via `SecretStore` at startup and populates the existing `token` field in memory. Existing code that reads `account.token` keeps working unchanged.

Backward compat: if `token` is present and `token_ref` is absent, migration runs on first startup and rewrites the file.

---

## Error handling

- **`keyring` backend missing** (rare on Linux): fall back to a warning + encrypted-at-rest file in `~/.claudeclaw/secrets.json` with 0600 perms. Mac/Windows always have a working backend.
- **Token validation fails** (`getMe` returns 401): abort `bind_channel`, don't write anything, return error with the API response.
- **`router.add_account` fails**: roll back the config write and the keyring entry. All-or-nothing.
- **iMessage on Windows**: `list_imessage_chats` and `bind_channel(channel="imessage")` return a clear error directing user to run from the Mac.
- **Duplicate agent name**: `create_agent` refuses; suggests `{name}2`.

---

## Testing

New tests in `tests/`:

- `test_secret_store.py` — set/get/delete/list, migration from plaintext config, idempotency
- `test_router_hot_reload.py` — add_account spawns a thread, remove_account stops it (uses a fake channel)
- `test_create_agent_tool.py` — scaffold produces valid files, rejects duplicates, renders placeholders
- `test_bind_channel_tool.py` — validates token, writes keyring, updates config, calls router (mocked)
- `test_imessage_chat_listing.py` — macOS only; skipped on Windows CI

All gated tools tested with the approval layer mocked.

---

## Build order

1. `SecretStore` + `keyring` dep + migration (no behavior change, unlocks everything else) — **smallest blast radius, commit first**
2. `AccountConfig.token_ref` + loader resolution
3. `router.add_account` / `remove_account` + thread-safety
4. `agents/_template/` + update `main` and `builder` AGENT.md with spawning section
5. `create_agent` tool
6. `bind_channel` tool with per-channel dispatch
7. `list_imessage_chats` helper
8. Docs: `docs/creating-agents.md`
9. Tests throughout, not batched at the end

Each step is a separate commit so review is easy.

---

## Open issues / deferred

- **Agent deletion** (`delete_agent` + `router.remove_account` wiring) — reserved in interface, not implemented in v1. Add when needed.
- **Discord/Slack automatic server/workspace install** — not possible, always manual step.
- **WhatsApp** — excluded per non-goals.
- **Config file locking during concurrent writes** — v1 assumes single-writer (one runtime process); if we ever run multiple, add `fcntl`/`msvcrt` locking.

---

## Bottom line

Four clean units: `SecretStore`, hot reload, provisioning tools, agent template. Each independently testable. New agents spawn from a template that teaches them to spawn further agents, so the capability propagates without per-agent patches. Tokens go to the OS keyring on day one, so `config.json` stops being a credential vault. Mac and Windows both work (iMessage binding is Mac-only by nature, cleanly errored on Windows).
