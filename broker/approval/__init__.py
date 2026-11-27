"""The trust boundary: only the *user* can approve a fill or supply a secret.

An approval is a single yes / no (one tap on the phone, one key in the terminal). There is no
PIN or authenticator step: on a phone the user has unlocked, it would guard only what that
phone already exposes (retired 2026-11-27).

  request.py   what is being approved (never secret) + secret normalisation
  terminal.py  the desktop channel (phone channel: ../phone/approver.py)
  window.py    opens the terminal channel in a window on this machine

Secrets returned by an approver are held in memory only and are never printed, logged or
returned to the agent.
"""
from typing import Protocol

from .request import Request


class Approver(Protocol):
    def approve(self, req: Request) -> bool: ...
    def secret(self, req: Request, what: str, optional: bool = False) -> str | None: ...


from .terminal import TerminalApprover  # noqa: E402

__all__ = ["Approver", "Request", "TerminalApprover"]
