"""A small dialog for secrets the user types (code, CVC, password, card), with Approve / Deny,
via `zenity --forms`. Values come back on a pipe to this process only: never in arguments,
files or logs. Linux only."""
from __future__ import annotations

import html
import os
import shutil
import subprocess
import time

from ..errors import BrokerError

SEP = "\x1f"              # unit separator: can't be typed into a field
LABELS = {"one-time code": "Code", "cvc": "Security code (CVC)", "card_number": "Card number",
          "expiry": "Expiry (MM/YY)", "password": "Password"}


def available() -> bool:
    return shutil.which("zenity") is not None


def ask(title: str, text: str, asks: list[str], deadline: float) -> dict[str, str] | None:
    """Shows one hidden field per ask. Returns {what: value} on Approve, None on Deny / close /
    timeout."""
    if not available():
        raise BrokerError("typing a secret on this computer needs zenity (apt install zenity)")
    left = int(deadline - time.time())
    if left <= 0:
        return None
    cmd = ["zenity", "--forms", f"--title={title}", f"--text={html.escape(text)}",
           "--ok-label=Approve", "--cancel-label=Deny", f"--separator={SEP}", f"--timeout={left}"]
    cmd += [f"--add-password={LABELS.get(w, w)}" for w in asks]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    _bring_forward(proc.pid)
    try:
        out, _ = proc.communicate(timeout=left + 5)
    except subprocess.TimeoutExpired:
        proc.kill()
        return None
    if proc.returncode != 0:                       # 1 = Deny / closed, 5 = timed out
        return None
    values = out.rstrip("\n").split(SEP)
    if len(values) != len(asks):
        raise BrokerError("the dialog returned an unexpected number of fields")
    return dict(zip(asks, values))


def _bring_forward(pid: int, wait_s: float = 3.0) -> None:
    """On X11, raise the dialog once it appears: GNOME would leave it under the browser."""
    if os.environ.get("XDG_SESSION_TYPE") == "wayland" or not os.environ.get("DISPLAY"):
        return
    from ..desktop import x11
    end = time.time() + wait_s
    while time.time() < end:
        if wins := [w for w in x11.windows(pid) if w.title]:
            x11.bring_to_front(wins[0])
            return
        time.sleep(0.1)
