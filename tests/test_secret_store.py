from __future__ import annotations

import keyring
from keyring.backend import KeyringBackend

from app.secret_store import SecretStore


class MemoryKeyring(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def get_password(self, service, username):
        return self._store.get((service, username))

    def delete_password(self, service, username):
        self._store.pop((service, username), None)


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


def test_username_format():
    s = SecretStore()
    assert s._username("finance", "telegram") == "finance:telegram"
