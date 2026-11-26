"""Approval-method state (PIN hash, authenticator secret, failure counters), one JSON value
per method in the broker's vault (the OS keyring by default; see vault.py).

A 4-digit PIN hash is cheap to brute-force offline, so the PIN only means something while
this state stays private; the keyring keeps it encrypted at rest.
"""
from __future__ import annotations

import json

from ..vault import Vault, open_vault

_vault: Vault | None = None


def _v() -> Vault:
    global _vault
    if _vault is None:
        _vault = open_vault()
    return _vault


def _key(name: str) -> str:
    return f"approval/{name}"


def section(name: str) -> dict:
    raw = _v().get(_key(name))
    return json.loads(raw) if raw else {}


def update(name: str, **fields) -> None:
    _v().set(_key(name), json.dumps({**section(name), **fields}))


def remove(name: str) -> None:
    _v().delete(_key(name))
