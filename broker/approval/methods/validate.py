"""validate: a single yes/no action, nothing typed."""
from __future__ import annotations

from ..request import Request
from .base import Verdict


class ValidateOnly:
    """Binary: the channel's Approve action ("y" key in the terminal, a button on the phone)."""
    name, tap, hidden = "validate", True, False
    APPROVE = "y"

    def ready(self) -> None:
        pass

    def prompt(self, req: Request) -> str:
        return "Press y to approve, any other key to cancel "

    def check(self, req: Request, answer: str) -> Verdict:
        return Verdict.APPROVED if answer.lower() == self.APPROVE else Verdict.CANCELLED
