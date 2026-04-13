# Agent Self-Provisioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let running agents scaffold new agents and bind per-channel bot credentials (Telegram/Discord/Slack/iMessage) with hot router reload, no restart, tokens stored in OS keyring.

**Architecture:** Four isolated units — `SecretStore` (keyring wrapper), `AccountConfig.token_ref` + loader resolution, `router.add_account` hot reload, and `create_agent`/`bind_channel` tools backed by an `agents/_template/` scaffold.

**Tech Stack:** Python 3.11+, `keyring>=24`, existing `AssistantRouter`/`ToolRegistry`, stdlib `urllib` for token validation, macOS Messages `chat.db` for iMessage chat listing.

**Spec:** `docs/superpowers/specs/2026-04-13-agent-self-provisioning-design.md`

---

## Task 1: SecretStore + keyring dep

**Files:**
- Create: `app/secret_store.py`
- Create: `tests/test_secret_store.py`
- Modify: `pyproject.toml` (add `keyring>=24` to base deps)

- [ ] **Step 1:** Add `keyring>=24` to `pyproject.toml` dependencies list.

- [ ] **Step 2:** Write `app/secret_store.py`:

```python
from __future__ import annotations

import keyring
from keyring.errors import KeyringError

SERVICE = "claudeclaw"


class SecretStoreError(Exception):
    pass


class SecretStore:
    """Thin wrapper around the OS secret store (Keychain/Credential Manager)."""

    def __init__(self, service: str = SERVICE) -> None:
        self._service = service

    def _username(self, agent: str, channel: str) -> str:
        return f"{agent}:{channel}"

    def set(self, agent: str, channel: str, token: str) -> None:
        try:
            keyring.set_password(self._service, self._username(agent, channel), token)
        except KeyringError as exc:
            raise SecretStoreError(f"Failed to store secret for {agent}:{channel}: {exc}") from exc

    def get(self, agent: str, channel: str) -> str | None:
        try:
            return keyring.get_password(self._service, self._username(agent, channel))
        except KeyringError as exc:
            raise SecretStoreError(f"Failed to read secret for {agent}:{channel}: {exc}") from exc

    def delete(self, agent: str, channel: str) -> None:
        try:
            keyring.delete_password(self._service, self._username(agent, channel))
        except keyring.errors.PasswordDeleteError:
            pass
        except KeyringError as exc:
            raise SecretStoreError(f"Failed to delete secret for {agent}:{channel}: {exc}") from exc
```

- [ ] **Step 3:** Write `tests/test_secret_store.py` using `keyring.backends.fail.Keyring` or a fake backend via `keyring.set_keyring`:

```python
import keyring
from keyring.backend import KeyringBackend
from app.secret_store import SecretStore


class MemoryKeyring(KeyringBackend):
    priority = 1
    def __init__(self): self._store = {}
    def set_password(self, service, username, password): self._store[(service, username)] = password
    def get_password(self, service, username): return self._store.get((service, username))
    def delete_password(self, service, username): self._store.pop((service, username), None)


def _install_fake():
    keyring.set_keyring(MemoryKeyring())


def test_set_and_get():
    _install_fake()
    s = SecretStore()
    s.set("finance", "telegram", "tok123")
    assert s.get("finance", "telegram") == "tok123"


def test_get_missing_returns_none():
    _install_fake()
    s = SecretStore()
    assert s.get("nope", "telegram") is None


def test_delete():
    _install_fake()
    s = SecretStore()
    s.set("finance", "telegram", "tok")
    s.delete("finance", "telegram")
    assert s.get("finance", "telegram") is None


def test_delete_missing_is_noop():
    _install_fake()
    s = SecretStore()
    s.delete("nope", "telegram")
```

- [ ] **Step 4:** Run `pytest tests/test_secret_store.py -v`. Expected: 4 passed.

- [ ] **Step 5:** Commit: `git add app/secret_store.py tests/test_secret_store.py pyproject.toml && git commit -m "feat: add SecretStore (keyring wrapper) for per-agent credentials"`

---

## Task 2: AccountConfig.token_ref + loader resolution

**Files:**
- Modify: `app/config.py` — add `token_ref` optional field + resolution

- [ ] **Step 1:** Edit `AccountConfig` dataclass in `app/config.py`:

```python
@dataclass(frozen=True)
class AccountConfig:
    id: str
    platform: str
    token: str
    allowed_chat_ids: list[str]
    channel_config: dict[str, Any] | None = None
    token_ref: str | None = None
```

- [ ] **Step 2:** In `_parse_accounts`, replace the hard `token=_require_string(...)` with token-or-token_ref resolution. When `token_ref` is present, look it up via `SecretStore`; when `token` is present plaintext, keep it (backward compat). Error if neither.

```python
from .secret_store import SecretStore

# inside the for loop, replacing token=_require_string(...):
token_ref = account_raw.get("token_ref")
raw_token = account_raw.get("token")
if token_ref:
    if not isinstance(token_ref, str) or not token_ref.strip():
        raise ConfigError(f"Invalid token_ref for account: {cleaned_account_id}")
    agent_name, _, channel_name = token_ref.partition(":")
    if not agent_name or not channel_name:
        raise ConfigError(f"token_ref must be 'agent:channel' for account: {cleaned_account_id}")
    resolved = SecretStore().get(agent_name, channel_name)
    if resolved is None:
        raise ConfigError(f"No secret found in keyring for token_ref: {token_ref}")
    token_value = resolved
elif isinstance(raw_token, str) and raw_token.strip():
    token_value = raw_token
elif platform.lower() == "imessage":
    token_value = ""  # iMessage has no token
else:
    raise ConfigError(f"Missing token/token_ref for account: {cleaned_account_id}")

# Build AccountConfig with token=token_value and token_ref=token_ref
account = AccountConfig(
    id=cleaned_account_id,
    platform=platform.lower(),
    token=token_value,
    allowed_chat_ids=account_raw.get("allowed_chat_ids", []) if platform.lower() == "imessage" else _require_string_list(account_raw, "allowed_chat_ids"),
    channel_config=channel_config,
    token_ref=token_ref if isinstance(token_ref, str) else None,
)
```

- [ ] **Step 3:** Run `pytest tests/test_config.py -v` (if exists) or `pytest -v -k config`. Fix any regressions.

- [ ] **Step 4:** Commit: `git commit -am "feat: resolve AccountConfig token via SecretStore when token_ref set"`

---

## Task 3: Router hot reload (`add_account`)

**Files:**
- Modify: `app/router.py` — add `_accounts_lock`, `add_account`, `remove_account` (stub)

- [ ] **Step 1:** In `AssistantRouter.__init__`, add `self._accounts_lock = threading.Lock()` and `self._active_workers: dict[str, threading.Thread] = {}`.

- [ ] **Step 2:** Refactor `_start_account_workers` so each spawned thread is registered in `self._active_workers[account.id]`.

- [ ] **Step 3:** Add method:

```python
def add_account(self, account_id: str) -> None:
    """Hot-add a new account: reload config, spawn polling thread, start event-driven channel."""
    from .config import load_config
    with self._accounts_lock:
        new_config = load_config(self._config_path)
        if account_id not in new_config.accounts:
            raise ValueError(f"Account {account_id!r} not in config after reload")
        self._config = new_config
        account = new_config.accounts[account_id]
        if account.platform in {"discord", "slack"}:
            self._start_event_driven_channel_for_account(account)
        else:
            thread = threading.Thread(
                target=self._account_worker,
                args=(account,),
                name=f"account-{account_id}",
                daemon=True,
            )
            thread.start()
            self._active_workers[account_id] = thread
        LOGGER.info("Account hot-added account_id=%s platform=%s", account_id, account.platform)
```

Note: reuse whatever method name `_start_account_workers` calls per-account. If the existing code doesn't have a single-account start, extract one.

- [ ] **Step 4:** Confirm `self._config_path` is stored on init. If not, add it. Run `pytest tests/test_router.py -v` if available.

- [ ] **Step 5:** Commit: `git commit -am "feat: router.add_account hot-loads new accounts without restart"`

---

## Task 4: `agents/_template/`

**Files:**
- Create: `agents/_template/agent.json`
- Create: `agents/_template/AGENT.md`
- Create: `agents/_template/TOOLS.md`

- [ ] **Step 1:** `agents/_template/agent.json`:

```json
{
  "display_name": "{{display_name}}",
  "description": "{{description}}",
  "model": "opus",
  "effort": "high",
  "safe_commands": [],
  "working_dir": null,
  "computer_use": false,
  "computer_use_auto_approve": false
}
```

- [ ] **Step 2:** `agents/_template/AGENT.md`:

```markdown
# {{display_name}}

{{persona}}

## Spawning Sub-Agents

You can create new sibling agents on the user's request. Use these tools in order:

1. `create_agent(name, persona, description?)` — scaffolds a new agent folder from this template.
2. `bind_channel(agent, channel, ...)` — binds a bot token (Telegram/Discord/Slack) or routing rule (iMessage) to the new agent. Hot-loads into the running process; no restart.
3. `list_imessage_chats()` — lists recent Messages.app group chats with their chat_identifier, for iMessage binding. macOS only.

When binding channels, guide the user through the manual steps at `@BotFather` (Telegram), discord.com/developers (Discord), api.slack.com/apps (Slack), or Messages.app (iMessage). Each `bind_channel` call takes the token/chat_identifier the user pastes back and wires it in.

Tokens are stored in the OS secret store (Keychain/Credential Manager), never plaintext config.
```

- [ ] **Step 3:** `agents/_template/TOOLS.md`:

```markdown
# Tools Available

All standard tools are available: web_search, web_fetch, read_file, write_file, list_dir, disk_usage, list_processes, run_command, create_agent, bind_channel.

`run_command` is gated behind YES/NO approval unless the command matches an entry in `agent.json::safe_commands`.

`create_agent` and `bind_channel` write to config and the OS keyring; use them only when the user explicitly asks to spawn a new agent.
```

- [ ] **Step 4:** Commit: `git add agents/_template && git commit -m "feat: add agents/_template/ scaffold for spawned agents"`

---

## Task 5: `create_agent` tool

**Files:**
- Create: `app/agent_provisioning.py` — scaffolding logic
- Modify: `app/tools.py` — register `create_agent`
- Create: `tests/test_agent_provisioning.py`

- [ ] **Step 1:** `app/agent_provisioning.py`:

```python
from __future__ import annotations

import re
import shutil
from pathlib import Path

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")


class ProvisioningError(Exception):
    pass


def validate_agent_name(name: str) -> str:
    name = name.strip().lower()
    if not _NAME_RE.match(name):
        raise ProvisioningError(
            f"Invalid agent name {name!r}. Use lowercase letters, digits, dashes; 1-32 chars."
        )
    if name in {"_template", "main"}:
        if name == "_template":
            raise ProvisioningError("'_template' is reserved")
    return name


def scaffold_agent(
    agents_dir: Path,
    name: str,
    display_name: str,
    persona: str,
    description: str = "",
) -> Path:
    name = validate_agent_name(name)
    target = agents_dir / name
    if target.exists():
        raise ProvisioningError(f"Agent {name!r} already exists at {target}")
    template = agents_dir / "_template"
    if not template.exists():
        raise ProvisioningError(f"Template not found at {template}")
    shutil.copytree(template, target)
    # Render placeholders
    replacements = {
        "{{display_name}}": display_name,
        "{{description}}": description,
        "{{persona}}": persona,
    }
    for file_name in ("agent.json", "AGENT.md", "TOOLS.md"):
        path = target / file_name
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        for k, v in replacements.items():
            content = content.replace(k, v)
        path.write_text(content, encoding="utf-8")
    return target
```

- [ ] **Step 2:** Register in `app/tools.py::build_default_registry`. Need agents_dir — add optional param:

```python
def build_default_registry(
    working_directory: str | Path | None = None,
    agents_dir: Path | None = None,
    router: "AssistantRouter | None" = None,
) -> ToolRegistry:
    ...
    if agents_dir is not None:
        from .agent_provisioning import scaffold_agent, ProvisioningError
        def _create_agent(args: dict) -> str:
            try:
                name = args.get("name", "").strip()
                display_name = args.get("display_name") or name.title()
                persona = args.get("persona", "").strip()
                description = args.get("description", "").strip()
                if not name or not persona:
                    return "Error: create_agent requires 'name' and 'persona'"
                target = scaffold_agent(agents_dir, name, display_name, persona, description)
                return (
                    f"Agent {name!r} scaffolded at {target}.\n\n"
                    f"Next: call bind_channel(agent={name!r}, channel='telegram'|'discord'|'slack'|'imessage', ...) "
                    f"to wire up communication."
                )
            except ProvisioningError as exc:
                return f"Error: {exc}"
        registry.register(
            ToolSpec(
                name="create_agent",
                description="Scaffold a new sibling agent from the template. Creates agents/<name>/ with agent.json, AGENT.md, TOOLS.md.",
                arguments={
                    "name": "lowercase alnum+dash, 1-32 chars (e.g. 'finance')",
                    "display_name": "optional human-readable name (defaults to Title-cased name)",
                    "persona": "persona paragraph for the new agent's AGENT.md",
                    "description": "optional short description",
                },
            ),
            _create_agent,
        )
```

- [ ] **Step 3:** Update callers of `build_default_registry` in `router.py` / `tools.py` / `assistant_cli.py` to pass `agents_dir` and `router` where available. `grep -rn "build_default_registry(" app/` to find them.

- [ ] **Step 4:** `tests/test_agent_provisioning.py`:

```python
from pathlib import Path
import pytest
from app.agent_provisioning import scaffold_agent, validate_agent_name, ProvisioningError


def _setup_template(root: Path) -> Path:
    agents = root / "agents"
    template = agents / "_template"
    template.mkdir(parents=True)
    (template / "agent.json").write_text('{"display_name": "{{display_name}}"}')
    (template / "AGENT.md").write_text("# {{display_name}}\n\n{{persona}}")
    (template / "TOOLS.md").write_text("tools for {{display_name}}")
    return agents


def test_scaffold_creates_files(tmp_path):
    agents = _setup_template(tmp_path)
    target = scaffold_agent(agents, "finance", "Finance", "You track money.")
    assert (target / "agent.json").read_text() == '{"display_name": "Finance"}'
    assert "# Finance" in (target / "AGENT.md").read_text()
    assert "You track money." in (target / "AGENT.md").read_text()


def test_scaffold_rejects_duplicate(tmp_path):
    agents = _setup_template(tmp_path)
    scaffold_agent(agents, "finance", "Finance", "p")
    with pytest.raises(ProvisioningError, match="already exists"):
        scaffold_agent(agents, "finance", "Finance", "p")


def test_validate_rejects_bad_name():
    with pytest.raises(ProvisioningError):
        validate_agent_name("Bad Name!")
    with pytest.raises(ProvisioningError):
        validate_agent_name("_template")


def test_validate_normalizes_case():
    assert validate_agent_name("FINANCE") == "finance"
```

- [ ] **Step 5:** Run `pytest tests/test_agent_provisioning.py -v`. Expected: 4 passed.

- [ ] **Step 6:** Commit: `git commit -am "feat: create_agent tool scaffolds new agents from template"`

---

## Task 6: `bind_channel` tool + iMessage helper

**Files:**
- Modify: `app/agent_provisioning.py` — add `bind_channel_impl` with per-channel dispatch
- Modify: `app/tools.py` — register `bind_channel`, `list_imessage_chats`
- Create: `tests/test_bind_channel.py`

- [ ] **Step 1:** Add to `app/agent_provisioning.py`:

```python
import json
import os
import sqlite3
import urllib.error
import urllib.request
from .secret_store import SecretStore


def _telegram_get_me(token: str) -> dict:
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/getMe")
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if not body.get("ok"):
        raise ProvisioningError(f"Telegram getMe failed: {body}")
    return body["result"]


def _discord_get_me(token: str) -> dict:
    req = urllib.request.Request(
        "https://discord.com/api/v10/users/@me",
        headers={"Authorization": f"Bot {token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _slack_auth_test(token: str) -> dict:
    req = urllib.request.Request(
        "https://slack.com/api/auth.test",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if not body.get("ok"):
        raise ProvisioningError(f"Slack auth.test failed: {body.get('error')}")
    return body


def bind_channel_impl(
    config_path: Path,
    agent: str,
    channel: str,
    *,
    token: str | None = None,
    app_token: str | None = None,
    chat_identifier: str | None = None,
    secret_store: SecretStore | None = None,
) -> dict:
    channel = channel.lower().strip()
    if channel not in {"telegram", "discord", "slack", "imessage"}:
        raise ProvisioningError(f"Unsupported channel: {channel}")
    store = secret_store or SecretStore()

    # 1. Validate token(s)
    if channel == "telegram":
        if not token:
            raise ProvisioningError("Telegram bind requires 'token'")
        try:
            info = _telegram_get_me(token)
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            raise ProvisioningError(f"Telegram token validation failed: {exc}")
        display = f"@{info.get('username', '?')}"
    elif channel == "discord":
        if not token:
            raise ProvisioningError("Discord bind requires 'token'")
        try:
            info = _discord_get_me(token)
        except Exception as exc:
            raise ProvisioningError(f"Discord token validation failed: {exc}")
        display = info.get("username", "?")
    elif channel == "slack":
        if not token or not app_token:
            raise ProvisioningError("Slack bind requires 'token' and 'app_token'")
        try:
            info = _slack_auth_test(token)
        except Exception as exc:
            raise ProvisioningError(f"Slack token validation failed: {exc}")
        display = info.get("user", "?")
    elif channel == "imessage":
        if not chat_identifier:
            raise ProvisioningError("iMessage bind requires 'chat_identifier'")
        display = chat_identifier
        info = {"chat_identifier": chat_identifier}

    # 2. Write secrets
    if channel in {"telegram", "discord", "slack"}:
        store.set(agent, channel, token)
    if channel == "slack":
        store.set(agent, "slack-app", app_token)

    # 3. Update config
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    accounts = cfg.setdefault("accounts", {})
    account_id = f"{agent}-{channel}"
    entry = {
        "platform": channel,
        "agent": agent,
    }
    if channel in {"telegram", "discord", "slack"}:
        entry["token_ref"] = f"{agent}:{channel}"
        entry["allowed_chat_ids"] = []
    if channel == "slack":
        entry["channel_config"] = {"app_token_ref": f"{agent}:slack-app"}
    if channel == "imessage":
        entry["chat_identifier"] = chat_identifier
        entry["allowed_chat_ids"] = [chat_identifier]
    accounts[account_id] = entry
    routing = cfg.setdefault("routing", {})
    routing[account_id] = {"default_agent": agent, "chat_agent_map": {}}
    config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    return {"account_id": account_id, "display": display, "channel": channel}


def list_imessage_chats_impl(limit: int = 20) -> list[dict]:
    if os.name == "nt":
        raise ProvisioningError("iMessage listing requires macOS")
    db = Path.home() / "Library" / "Messages" / "chat.db"
    if not db.exists():
        raise ProvisioningError(f"Messages database not found at {db}")
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT chat_identifier, display_name FROM chat ORDER BY ROWID DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [{"chat_identifier": cid, "display_name": name or ""} for cid, name in rows]
```

- [ ] **Step 2:** Register `bind_channel` and `list_imessage_chats` in `tools.py`:

```python
if agents_dir is not None:
    from .agent_provisioning import bind_channel_impl, list_imessage_chats_impl, ProvisioningError
    _config_path = getattr(router, "_config_path", None) if router else None
    def _bind_channel(args: dict) -> str:
        try:
            if _config_path is None:
                return "Error: router/config_path unavailable"
            result = bind_channel_impl(
                Path(_config_path),
                agent=args.get("agent", "").strip(),
                channel=args.get("channel", "").strip(),
                token=args.get("token"),
                app_token=args.get("app_token"),
                chat_identifier=args.get("chat_identifier"),
            )
            if router is not None:
                router.add_account(result["account_id"])
            return (
                f"Bound {result['channel']} channel for agent {args.get('agent')!r} "
                f"({result['display']}). Account id: {result['account_id']}. "
                f"Runtime reloaded — new bot is live."
            )
        except ProvisioningError as exc:
            return f"Error: {exc}"
    registry.register(
        ToolSpec(
            name="bind_channel",
            description=(
                "Bind a communication channel to an agent. Validates credentials, stores token in OS keyring, "
                "updates config, hot-reloads router. Channels: telegram, discord, slack, imessage."
            ),
            arguments={
                "agent": "target agent name (must already exist)",
                "channel": "one of: telegram, discord, slack, imessage",
                "token": "bot token (Telegram/Discord/Slack bot token)",
                "app_token": "Slack app-level token (xapp-...)",
                "chat_identifier": "iMessage chat_identifier from list_imessage_chats",
            },
        ),
        _bind_channel,
    )
    def _list_imessage_chats(args: dict) -> str:
        try:
            limit = int(args.get("limit", 20))
            chats = list_imessage_chats_impl(limit=limit)
            if not chats:
                return "No recent iMessage chats found."
            lines = [f"{i+1}. {c['display_name'] or '(no name)'} — {c['chat_identifier']}" for i, c in enumerate(chats)]
            return "Recent iMessage chats:\n" + "\n".join(lines)
        except ProvisioningError as exc:
            return f"Error: {exc}"
    registry.register(
        ToolSpec(
            name="list_imessage_chats",
            description="List recent Messages.app chats with their chat_identifier (for iMessage channel binding). macOS only.",
            arguments={"limit": "max chats to return (default 20)"},
        ),
        _list_imessage_chats,
    )
```

- [ ] **Step 3:** `tests/test_bind_channel.py` — test config writing with mocked validators and secret store:

```python
import json
from pathlib import Path
from unittest.mock import patch
from app.agent_provisioning import bind_channel_impl, ProvisioningError
from app.secret_store import SecretStore
import pytest


class FakeStore:
    def __init__(self): self.items = {}
    def set(self, a, c, t): self.items[(a, c)] = t
    def get(self, a, c): return self.items.get((a, c))
    def delete(self, a, c): self.items.pop((a, c), None)


def _seed_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"accounts": {}, "routing": {}}))
    return cfg


def test_telegram_bind_writes_config(tmp_path):
    cfg = _seed_config(tmp_path)
    store = FakeStore()
    with patch("app.agent_provisioning._telegram_get_me", return_value={"username": "fin_bot"}):
        bind_channel_impl(cfg, "finance", "telegram", token="123:abc", secret_store=store)
    data = json.loads(cfg.read_text())
    assert "finance-telegram" in data["accounts"]
    assert data["accounts"]["finance-telegram"]["token_ref"] == "finance:telegram"
    assert store.items[("finance", "telegram")] == "123:abc"


def test_imessage_bind_no_token(tmp_path):
    cfg = _seed_config(tmp_path)
    store = FakeStore()
    bind_channel_impl(cfg, "finance", "imessage", chat_identifier="chat12345", secret_store=store)
    data = json.loads(cfg.read_text())
    assert data["accounts"]["finance-imessage"]["chat_identifier"] == "chat12345"
    assert store.items == {}


def test_slack_bind_requires_both_tokens(tmp_path):
    cfg = _seed_config(tmp_path)
    with pytest.raises(ProvisioningError, match="app_token"):
        bind_channel_impl(cfg, "finance", "slack", token="xoxb-x", secret_store=FakeStore())
```

- [ ] **Step 4:** Run `pytest tests/test_bind_channel.py -v`. Expected: 3 passed.

- [ ] **Step 5:** Commit: `git commit -am "feat: bind_channel tool + list_imessage_chats helper"`

---

## Task 7: Update main AGENT.md with spawning section

**Files:**
- Modify: `agents/main/AGENT.md` — add "Spawning Sub-Agents" section (same content as template)

- [ ] **Step 1:** Append the same "Spawning Sub-Agents" section from `agents/_template/AGENT.md` to `agents/main/AGENT.md`. If `agents/main/AGENT.md` doesn't exist, create it.

- [ ] **Step 2:** Commit: `git commit -am "docs: teach main agent about create_agent/bind_channel"`

---

## Task 8: Full test run + handoff doc

- [ ] **Step 1:** `pytest -q` — full suite. Fix any breakage.

- [ ] **Step 2:** Write handoff note at `docs/handoff-2026-04-13.md` summarizing the feature.

- [ ] **Step 3:** Final commit: `git commit -am "docs: handoff for agent self-provisioning"`

- [ ] **Step 4:** Report done to user with test count and feature summary.

---

## Non-goals reminder

- WhatsApp: skipped per spec.
- Per-agent Apple IDs: not possible; iMessage shares single Apple ID, routes by `chat_identifier`.
- Automated Telegram/Discord/Slack account creation: impossible; interactive human step required.
- Agent deletion: `remove_account` reserved but not implemented.
