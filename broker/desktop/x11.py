"""Real X11 input and screen capture. Knows nothing about Chrome or web pages.

Tools: xdotool (windows, mouse, keyboard). X11 only (blocked on
Wayland). Input needs an unlocked desktop. Captures are on-screen pixels, so the window
must be visible.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

from ..errors import BrokerError

os.environ.setdefault("DISPLAY", ":0")


@dataclass(frozen=True)
class Window:
    id: str
    title: str
    x: int
    y: int
    width: int
    height: int

    @property
    def key(self) -> tuple:
        """Identity used to spot windows that appeared or changed."""
        return (self.id, self.width, self.height)


def _xdo(*args, timeout=5, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["xdotool", *args], capture_output=True, text=True,
                          timeout=timeout, input=stdin)


def screen_locked() -> bool:
    r = subprocess.run(["loginctl", "show-session", os.environ.get("XDG_SESSION_ID", "auto"),
                        "-p", "LockedHint", "--value"], capture_output=True, text=True)
    return r.stdout.strip() == "yes"


def windows(pid) -> list[Window]:
    """Visible top-level windows of a process, including override-redirect popups."""
    out = []
    for wid in _xdo("search", "--onlyvisible", "--pid", str(pid)).stdout.split():
        g = dict(l.split("=", 1) for l in _xdo("getwindowgeometry", "--shell", wid).stdout.splitlines() if "=" in l)
        try:
            w = Window(wid, _xdo("getwindowname", wid).stdout.strip(),
                       int(g["X"]), int(g["Y"]), int(g["WIDTH"]), int(g["HEIGHT"]))
        except (KeyError, ValueError):
            continue
        if w.width > 1 and w.height > 1:
            out.append(w)
    return out


def main_window(pid, title_hint: str = "") -> Window:
    """The process's titled window matching `title_hint`, else its largest titled window."""
    titled = [w for w in windows(pid) if w.title]
    match = [w for w in titled if title_hint and title_hint[:30] in w.title]
    pool = match or titled
    if not pool:
        raise BrokerError("browser window not found")
    return max(pool, key=lambda w: w.width * w.height)


def activate(win: Window) -> None:
    _xdo("windowactivate", "--sync", win.id)


def active_pid() -> str:
    return _xdo("getactivewindow", "getwindowpid").stdout.strip()


def click(x: int, y: int) -> None:
    """Real left click at screen coordinates. (No --sync: it hangs if already there.)"""
    _xdo("mousemove", str(int(x)), str(int(y)), "sleep", "0.15", "click", "1")


def key(*names: str) -> None:
    """Real key events to whatever has keyboard focus (e.g. Down, Return, Escape, ctrl+a)."""
    _xdo("key", "--clearmodifiers", *names)


def type_secret(secret: str) -> None:
    """Type a secret as real keystrokes into the focused element. Read from stdin (never
    argv, so not visible in ps); output discarded unread."""
    r = _xdo("type", "--delay", "60", "--file", "-", timeout=30, stdin=secret)
    ok = r.returncode == 0
    del r
    if not ok:
        raise BrokerError("typing failed")
