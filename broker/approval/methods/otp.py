"""otp: the 6-digit code from an authenticator app (TOTP). Each code works once; locks after
MAX_FAILURES wrong."""
from __future__ import annotations

from ...errors import BrokerError
from .. import store, totp
from ..request import Request, digits
from .base import Counted, Verdict, cancelled


def set_otp_secret(secret_b32: str, first_code: str) -> None:
    """Saved only once the user proves the authenticator shows the right codes."""
    ctr = totp.match(secret_b32, digits(first_code), after=-1)
    if ctr is None:
        raise BrokerError("that code doesn't match; nothing saved, run setup-otp again")
    store.remove("otp")
    store.update("otp", secret=secret_b32, last_counter=ctr, failures=0)


class Otp(Counted):
    name, tap, hidden = "otp", False, True

    def ready(self) -> None:
        self._ready("authenticator")

    def prompt(self, req: Request) -> str:
        return "Authenticator code to approve (hidden; Enter to cancel): "

    def check(self, req: Request, answer: str) -> Verdict:
        if cancelled(answer):
            return Verdict.CANCELLED
        s = self._ready("authenticator")
        ctr = totp.match(s["secret"], digits(answer), after=s.get("last_counter", -1))
        if ctr is None:
            return self._fail()
        store.update(self.name, last_counter=ctr, failures=0)   # each code works once
        return Verdict.APPROVED
