"""Approval channel: a person at an interactive terminal on this machine. Shows the request,
asks for a one-key yes (y), then collects any secrets the user types."""
from __future__ import annotations

import getpass
import sys
import termios
import tty

from ..errors import BrokerError
from .request import Request, normalise


class TerminalApprover:
    def __init__(self):
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise BrokerError("TerminalApprover needs an interactive terminal")

    def approve(self, req: Request) -> bool:
        print(f"\nRequest:  {req.kind}\nSite:     {req.site}\nCert:     {req.certificate}\n"
              f"Frame:    {req.frame}\nItem:     {req.label}\nAmount:   {req.amount or 'not detected'}")
        for w in req.warnings:
            print(f"WARNING:  {w}")
        return _one_key("Press y to approve, any other key to cancel ").lower() == "y"

    def secret(self, req: Request, what: str, optional: bool = False) -> str | None:
        hint = " (hidden; Enter to skip)" if optional else " (hidden)"
        value = getpass.getpass(f"{what} for {req.label}{hint}: ").strip()
        if not value:
            if optional:
                return None
            raise BrokerError(f"no {what} given")
        print(f"  ({len(value)} characters received)")
        return normalise(what, value)


def _one_key(prompt: str) -> str:
    """Read exactly one keypress. Anything typed before the prompt appeared (e.g. the Enter
    that launched the command) is discarded first, so it can't approve by accident."""
    fd = sys.stdin.fileno()
    print(prompt, end="", flush=True)
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        termios.tcflush(fd, termios.TCIFLUSH)
        key = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    print("approved" if key.lower() == "y" else "cancelled")
    return key
