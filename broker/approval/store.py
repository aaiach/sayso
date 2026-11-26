"""Approval-method state: PIN hash, authenticator secret, failure counters. One JSON file, mode 0600.

Planned: move the secrets into the OS keyring (encrypted at rest). Like any desktop secret
store, it doesn't stop other programs running as the same user; a 4-digit PIN hash is cheap to
brute-force offline, so the PIN only means something while this state stays private.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .. import config

PATH: Path = config.APPROVAL_STORE


def load() -> dict:
    try:
        return json.loads(PATH.read_text())
    except FileNotFoundError:
        return {}


def save(state: dict) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = PATH.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, PATH)


def section(name: str) -> dict:
    return load().get(name, {})


def update(name: str, **fields) -> None:
    state = load()
    state.setdefault(name, {}).update(fields)
    save(state)


def remove(name: str) -> None:
    state = load()
    state.pop(name, None)
    save(state)
