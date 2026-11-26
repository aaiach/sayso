"""pin: a 4-8 digit PIN, stored as a salted scrypt hash; locks after MAX_FAILURES wrong."""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from ...errors import BrokerError
from .. import store
from ..request import Request, digits
from .base import Counted, Verdict, cancelled

PIN_FORMAT = re.compile(r"\d{4,8}")


def _pin_hash(pin: str, salt: bytes) -> str:
    return hashlib.scrypt(pin.encode(), salt=salt, n=2 ** 15, r=8, p=1, maxmem=64 << 20).hex()


def set_pin(pin: str) -> None:
    pin = digits(pin)
    if not PIN_FORMAT.fullmatch(pin):
        raise BrokerError("PIN must be 4 to 8 digits")
    salt = secrets.token_bytes(16)
    store.remove("pin")
    store.update("pin", salt=salt.hex(), hash=_pin_hash(pin, salt), failures=0)


class Pin(Counted):
    name, tap, hidden = "pin", False, True

    def ready(self) -> None:
        self._ready("PIN")

    def prompt(self, req: Request) -> str:
        return "PIN to approve (hidden; Enter to cancel): "

    def check(self, req: Request, answer: str) -> Verdict:
        if cancelled(answer):
            return Verdict.CANCELLED
        s = self._ready("PIN")
        if hmac.compare_digest(_pin_hash(digits(answer), bytes.fromhex(s["salt"])), s["hash"]):
            store.update(self.name, failures=0)
            return Verdict.APPROVED
        return self._fail()
