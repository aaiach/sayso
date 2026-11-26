"""What every approval method looks like, and the lockout shared by the secret-based ones."""
from __future__ import annotations

from enum import Enum
from typing import Protocol

from ...errors import BrokerError
from .. import store
from ..request import Request

MAX_FAILURES = 5          # consecutive wrong PINs / codes before the method locks


class Verdict(Enum):
    APPROVED = "approved"
    WRONG = "wrong"
    CANCELLED = "cancelled"


class Method(Protocol):
    name: str
    tap: bool             # a single yes/no action (button / one key), nothing typed
    hidden: bool          # answer must not echo (and never reaches a log)

    def ready(self) -> None: ...                 # raises BrokerError if not set up or locked
    def prompt(self, req: Request) -> str: ...
    def check(self, req: Request, answer: str) -> Verdict: ...


def cancelled(answer: str) -> bool:
    return answer.strip().lower() in ("", "no", "n", "cancel")


class Counted:
    """Shared lockout for secret-based methods: MAX_FAILURES wrong answers in a row lock it."""
    name: str

    def _state(self) -> dict:
        return store.section(self.name)

    def _ready(self, what: str) -> dict:
        s = self._state()
        if not s:
            raise BrokerError(f"no {what} set up: run `broker.cli setup-{self.name}` first")
        if s.get("failures", 0) >= MAX_FAILURES:
            raise BrokerError(f"{what} locked after {MAX_FAILURES} wrong attempts: "
                              f"run `broker.cli setup-{self.name}` to reset it")
        return s

    def _fail(self) -> Verdict:
        store.update(self.name, failures=self._state().get("failures", 0) + 1)
        if self._state()["failures"] >= MAX_FAILURES:
            raise BrokerError(f"too many wrong attempts; {self.name} is now locked")
        return Verdict.WRONG
