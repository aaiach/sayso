"""Where the user answers an approval: the paired phone, or this computer (local mode).
Chosen by the broker from its configuration, never by the agent: the agent is the party being
checked, so it must not be able to pick the channel it could answer itself.

BROKER_APPROVER=auto (default): the paired phone when there is one (and a relay), else this
computer's desktop notifications. `phone` or `local` forces one.
"""
from __future__ import annotations

from . import config
from .errors import BrokerError

PHONE, LOCAL = "phone", "this computer"


def which() -> str:
    """The channel this request will use; raises BrokerError when there is none."""
    if config.APPROVER == "phone":
        return PHONE
    if config.APPROVER == "local":
        return LOCAL
    if config.APPROVER != "auto":
        raise BrokerError(f"BROKER_APPROVER must be auto, phone or local, not {config.APPROVER!r}")
    from .phone import keys
    if config.RELAY_URL and keys.device() is not None:
        return PHONE
    from .local import notify
    if notify.available():
        return LOCAL
    raise BrokerError("nowhere to ask for approval: pair a phone (`python -m broker.cli setup`) "
                      "or run on a desktop session with notifications")


def approver(channel: str, deadline: float):
    """The approver for `channel`; answers after `deadline` don't count."""
    if channel == PHONE:
        from .phone.approver import PhoneApprover
        return PhoneApprover()
    from .local.approver import LocalApprover
    return LocalApprover(deadline)
