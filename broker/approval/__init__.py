"""The trust boundary: only the *user* can approve a fill or supply a secret.

  request.py   what is being approved (never secret) + secret normalisation
  methods/     how an approval is proven: validate (one tap), PIN, authenticator code; one file each
  terminal.py  the channel the user answers on (terminal today, phone app later)
  setup.py     one-time PIN / authenticator setup
  store.py     method state (PIN hash, authenticator secret, lockout counters), mode 0600
  totp.py      RFC 6238 codes, stdlib only

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
