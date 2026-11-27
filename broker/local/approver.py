"""LocalApprover: approval on this computer, for agents running on the user's own machine while
they're at it. A notification with Approve / Deny, or a dialog when the request asks the user to
type something. No phone, relay or Noise: nothing leaves the machine.

Limit (see DESIGN.md "Local mode"): an agent running as the same user on this desktop could
click Approve itself. This stops an agent using a secret without asking, not one set on
getting around the check.
"""
from __future__ import annotations

import time

from ..approval.request import Request, normalise
from ..errors import BrokerError
from . import dialog, notify


def describe(req: Request) -> str:
    lines = [req.label or req.kind, f"on {req.site}"]
    if req.frame and req.frame != req.site:
        lines.append(f"in a frame from {req.frame}")
    if req.amount:
        lines.append(f"amount: {req.amount}")
    if req.certificate:
        lines.append(f"certificate: {req.certificate}")
    lines += [f"⚠ {w}" for w in req.warnings]
    return "\n".join(lines)


class LocalApprover:
    def __init__(self, deadline: float):
        notify.require()
        self.deadline = deadline
        self._typed: dict[str, str] = {}

    def approve(self, req: Request) -> bool:
        if time.time() > self.deadline:
            raise BrokerError("the request expired before it was shown")
        if req.asks:
            typed = dialog.ask("sayso: approve and type", describe(req),
                               [w for w, _ in req.asks], self.deadline)
            if typed is None:
                return False
            self._typed = {w: v for w, v in typed.items() if v}
            return True
        answer = notify.ask(f"sayso: approve {req.kind}?", describe(req).replace("\n", " · "),
                            self.deadline)        # notification banners flatten line breaks
        if answer == "timeout":
            raise BrokerError("no answer on this computer before the request expired")
        return answer == "approve"

    def secret(self, req: Request, what: str, optional: bool = False) -> str | None:
        """The value the user typed in the dialog for `what`, handed out once."""
        value = self._typed.pop(what, None)
        if not value:
            if optional:
                return None
            raise BrokerError(f"no {what} was typed")
        return normalise(what, value)
