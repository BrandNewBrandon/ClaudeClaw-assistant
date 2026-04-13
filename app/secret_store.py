from __future__ import annotations

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

SERVICE = "claudeclaw"


class SecretStoreError(Exception):
    pass


class SecretStore:
    """Thin wrapper around the OS secret store (Keychain/Credential Manager).

    Secrets are keyed by (agent, channel). Username format: "{agent}:{channel}".
    """

    def __init__(self, service: str = SERVICE) -> None:
        self._service = service

    def _username(self, agent: str, channel: str) -> str:
        return f"{agent}:{channel}"

    def set(self, agent: str, channel: str, token: str) -> None:
        try:
            keyring.set_password(self._service, self._username(agent, channel), token)
        except KeyringError as exc:
            raise SecretStoreError(
                f"Failed to store secret for {agent}:{channel}: {exc}"
            ) from exc

    def get(self, agent: str, channel: str) -> str | None:
        try:
            return keyring.get_password(self._service, self._username(agent, channel))
        except KeyringError as exc:
            raise SecretStoreError(
                f"Failed to read secret for {agent}:{channel}: {exc}"
            ) from exc

    def delete(self, agent: str, channel: str) -> None:
        try:
            keyring.delete_password(self._service, self._username(agent, channel))
        except PasswordDeleteError:
            pass
        except KeyringError as exc:
            raise SecretStoreError(
                f"Failed to delete secret for {agent}:{channel}: {exc}"
            ) from exc
