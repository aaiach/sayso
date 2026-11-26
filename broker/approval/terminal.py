"""Approval channel: a person at an interactive terminal on this machine (the phone app comes later).
Shows the request, asks for the approval with the chosen method, then collects secrets."""
from __future__ import annotations

import getpass
import sys
import termios
import tty

from ..errors import BrokerError
from . import methods
from .request import Request, normalise


class TerminalApprover:
    def __init__(self, method: str = "validate"):
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise BrokerError("TerminalApprover needs an interactive terminal")
        self.method = methods.get(method)
        self.method.ready()            # fail before touching the page if PIN/OTP isn't set up

    def approve(self, req: Request) -> bool:
        print(f"\nRequest:  {req.kind}\nSite:     {req.site}\nCert:     {req.certificate}\n"
              f"Frame:    {req.frame}\nItem:     {req.label}\nAmount:   {req.amount or 'not detected'}\n"
              f"Approve:  {self.method.name}")
        for w in req.warnings:
            print(f"WARNING:  {w}")
        if self.method.tap:
            return self.method.check(req, _one_key(self.method.prompt(req))) is methods.Verdict.APPROVED
        ask = getpass.getpass if self.method.hidden else input
        for _ in range(3):
            verdict = self.method.check(req, ask(self.method.prompt(req)))
            if verdict is methods.Verdict.APPROVED:
                return True
            if verdict is methods.Verdict.CANCELLED:
                return False
            print("Didn't match, try again.")
        return False

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
