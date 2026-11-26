"""Where the broker keeps its own secrets (PIN hash, authenticator secret, later the pairing
keys): named text values behind one tiny interface, so the backend can be swapped.

  keyring (default)  the OS secret store via the `keyring` library: Secret Service / GNOME
                     Keyring on Linux, Keychain on macOS. Encrypted at rest, unlocked with the
                     user's login.
  file               a 0600 JSON file, for machines without a secret store (headless, CI).
                     Not encrypted at rest: choose it explicitly (BROKER_SECRET_BACKEND=file).

Like any per-user secret store, neither stops other programs running as the same user.
"""
from __future__ import annotations

import json
import os
from typing import Protocol

from . import config
from .errors import BrokerError


class Vault(Protocol):
    def get(self, name: str) -> str | None: ...
    def set(self, name: str, value: str) -> None: ...
    def delete(self, name: str) -> None: ...


class KeyringVault:
    def __init__(self, service: str):
        import keyring
        from keyring.backends import fail
        if isinstance(keyring.get_keyring(), fail.Keyring):
            raise BrokerError("no OS secret store found; install one (e.g. gnome-keyring) "
                              "or set BROKER_SECRET_BACKEND=file in .env")
        self._kr, self.service = keyring, service

    def get(self, name: str) -> str | None:
        return self._kr.get_password(self.service, name)

    def set(self, name: str, value: str) -> None:
        self._kr.set_password(self.service, name, value)

    def delete(self, name: str) -> None:
        try:
            self._kr.delete_password(self.service, name)
        except self._kr.errors.PasswordDeleteError:
            pass


class FileVault:
    def __init__(self, path):
        self.path = path

    def _all(self) -> dict:
        try:
            with open(self.path) as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def _save(self, data: dict) -> None:
        os.makedirs(os.path.dirname(self.path), mode=0o700, exist_ok=True)
        tmp = f"{self.path}.tmp"
        with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            json.dump(data, f)
        os.replace(tmp, self.path)

    def get(self, name: str) -> str | None:
        return self._all().get(name)

    def set(self, name: str, value: str) -> None:
        self._save({**self._all(), name: value})

    def delete(self, name: str) -> None:
        data = self._all()
        if data.pop(name, None) is not None:
            self._save(data)


def open_vault() -> Vault:
    if config.SECRET_BACKEND == "keyring":
        return KeyringVault(config.KEYRING_SERVICE)
    if config.SECRET_BACKEND == "file":
        return FileVault(config.STATE_DIR / "secrets.json")
    raise BrokerError(f"unknown BROKER_SECRET_BACKEND {config.SECRET_BACKEND!r} (keyring or file)")
