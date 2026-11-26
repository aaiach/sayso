"""Approval window on the local desktop: runs one fill request in a new terminal window (where
the user approves and types secrets) and waits for its masked result. Stand-in until the
phone app; callers that run without a terminal of their own (the MCP server) use this.

The terminal command is `BROKER_TERMINAL` (default: gnome-terminal); it must run the given
command in a new window.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import uuid

from .. import config
from ..errors import BrokerError

TIMEOUT_S = 180       # approval expiry (120 s) + time to fill


def _runtime_dir() -> str:
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    d = os.path.join(base, "sayso")
    os.makedirs(d, mode=0o700, exist_ok=True)
    return d


def _write_private(path: str, data: dict) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)


def _open_window(cmd: list[str]) -> None:
    term = shlex.split(os.environ.get("BROKER_TERMINAL", "gnome-terminal --title=sayso-approval --"))
    env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}
    try:
        subprocess.Popen([*term, *cmd], env=env, cwd=config.ROOT, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise BrokerError(f"terminal {term[0]!r} not found; set BROKER_TERMINAL in .env")


def run(spec: dict, timeout: float = TIMEOUT_S) -> dict:
    """Open the approval window for `spec` (already validated) and return its result."""
    d, rid = _runtime_dir(), uuid.uuid4().hex
    spec_path, result_path = os.path.join(d, f"{rid}.spec.json"), os.path.join(d, f"{rid}.result.json")
    _write_private(spec_path, spec)
    deadline = time.time() + timeout
    _open_window([sys.executable, "-m", "broker.runner", spec_path, result_path, str(deadline - 10)])
    try:
        while time.time() < deadline:
            if os.path.exists(result_path):
                with open(result_path) as f:
                    return json.load(f)
            time.sleep(0.5)
        return {"status": "timeout", "reason": f"no answer within {int(timeout)} s"}
    finally:
        for p in (spec_path, result_path):
            if os.path.exists(p):
                os.unlink(p)
