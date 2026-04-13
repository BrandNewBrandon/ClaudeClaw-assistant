from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.agent_provisioning import (
    ProvisioningError,
    bind_channel_impl,
    list_imessage_chats_impl,
    scaffold_agent,
    validate_agent_name,
)


def _setup_template(root: Path) -> Path:
    agents = root / "agents"
    template = agents / "_template"
    template.mkdir(parents=True)
    (template / "agent.json").write_text('{"display_name": "{{display_name}}"}')
    (template / "AGENT.md").write_text("# {{display_name}}\n\n{{persona}}")
    (template / "TOOLS.md").write_text("tools for {{display_name}}")
    return agents


class FakeStore:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], str] = {}

    def set(self, agent: str, channel: str, token: str) -> None:
        self.items[(agent, channel)] = token

    def get(self, agent: str, channel: str) -> str | None:
        return self.items.get((agent, channel))

    def delete(self, agent: str, channel: str) -> None:
        self.items.pop((agent, channel), None)


# ---------- scaffold_agent ----------

def test_scaffold_creates_files(tmp_path):
    agents = _setup_template(tmp_path)
    target = scaffold_agent(agents, "finance", "Finance", "You track money.")
    assert (target / "agent.json").read_text() == '{"display_name": "Finance"}'
    content = (target / "AGENT.md").read_text()
    assert "# Finance" in content
    assert "You track money." in content


def test_scaffold_rejects_duplicate(tmp_path):
    agents = _setup_template(tmp_path)
    scaffold_agent(agents, "finance", "Finance", "p")
    with pytest.raises(ProvisioningError, match="already exists"):
        scaffold_agent(agents, "finance", "Finance", "p")


def test_scaffold_requires_template(tmp_path):
    agents = tmp_path / "agents"
    agents.mkdir()
    with pytest.raises(ProvisioningError, match="Template not found"):
        scaffold_agent(agents, "finance", "Finance", "p")


def test_validate_rejects_bad_name():
    with pytest.raises(ProvisioningError):
        validate_agent_name("Bad Name!")
    with pytest.raises(ProvisioningError):
        validate_agent_name("_template")
    with pytest.raises(ProvisioningError):
        validate_agent_name("-leading-dash")


def test_validate_normalizes_case():
    assert validate_agent_name("FINANCE") == "finance"
    assert validate_agent_name(" finance ") == "finance"


# ---------- bind_channel_impl ----------

def _seed_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"accounts": {}, "routing": {}}))
    return cfg


def test_telegram_bind_writes_config(tmp_path):
    cfg = _seed_config(tmp_path)
    store = FakeStore()
    with patch(
        "app.agent_provisioning._telegram_get_me",
        return_value={"username": "fin_bot", "id": 1},
    ):
        result = bind_channel_impl(
            cfg, "finance", "telegram", token="123:abc", secret_store=store
        )
    data = json.loads(cfg.read_text())
    assert result["account_id"] == "finance-telegram"
    assert result["display"] == "@fin_bot"
    assert "finance-telegram" in data["accounts"]
    entry = data["accounts"]["finance-telegram"]
    assert entry["token_ref"] == "finance:telegram"
    assert entry["platform"] == "telegram"
    assert entry["agent"] == "finance"
    assert store.items[("finance", "telegram")] == "123:abc"
    assert data["routing"]["finance-telegram"]["default_agent"] == "finance"


def test_imessage_bind_no_token(tmp_path):
    cfg = _seed_config(tmp_path)
    store = FakeStore()
    result = bind_channel_impl(
        cfg, "finance", "imessage", chat_identifier="chat12345", secret_store=store
    )
    data = json.loads(cfg.read_text())
    assert data["accounts"]["finance-imessage"]["chat_identifier"] == "chat12345"
    assert data["accounts"]["finance-imessage"]["allowed_chat_ids"] == ["chat12345"]
    assert store.items == {}
    assert result["display"] == "chat12345"


def test_imessage_bind_requires_chat_id(tmp_path):
    cfg = _seed_config(tmp_path)
    with pytest.raises(ProvisioningError, match="chat_identifier"):
        bind_channel_impl(cfg, "finance", "imessage", secret_store=FakeStore())


def test_slack_bind_requires_both_tokens(tmp_path):
    cfg = _seed_config(tmp_path)
    with pytest.raises(ProvisioningError, match="app_token"):
        bind_channel_impl(cfg, "finance", "slack", token="xoxb-x", secret_store=FakeStore())


def test_slack_bind_stores_both_tokens(tmp_path):
    cfg = _seed_config(tmp_path)
    store = FakeStore()
    with patch(
        "app.agent_provisioning._slack_auth_test",
        return_value={"ok": True, "user": "finbot"},
    ):
        bind_channel_impl(
            cfg,
            "finance",
            "slack",
            token="xoxb-bot",
            app_token="xapp-app",
            secret_store=store,
        )
    assert store.items[("finance", "slack")] == "xoxb-bot"
    assert store.items[("finance", "slack-app")] == "xapp-app"
    data = json.loads(cfg.read_text())
    assert data["accounts"]["finance-slack"]["channel_config"] == {
        "app_token_ref": "finance:slack-app"
    }


def test_bind_rejects_unknown_channel(tmp_path):
    cfg = _seed_config(tmp_path)
    with pytest.raises(ProvisioningError, match="Unsupported channel"):
        bind_channel_impl(cfg, "finance", "fax", token="t", secret_store=FakeStore())


# ---------- list_imessage_chats ----------

def test_list_imessage_on_windows_errors(monkeypatch):
    monkeypatch.setattr("os.name", "nt")
    with pytest.raises(ProvisioningError, match="requires macOS"):
        list_imessage_chats_impl()
