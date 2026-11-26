"""The three ways a user can approve a request. Each one decides only "is this answer an
approval?". Showing the request and collecting the answer belong to the channel (terminal
today, phone app later); choosing the method for a request belongs to the caller (a CLI flag
for now; a risk policy may come later).

  validate.py  one tap / one key (y): proves someone is at the approval channel
  pin.py       a 4-8 digit PIN (`broker.cli setup-pin`): proves they know the PIN
  otp.py       a 6-digit authenticator code (`broker.cli setup-otp`): proves they hold that phone
  base.py      the Method interface, Verdict, shared lockout
"""
from ...errors import BrokerError
from .base import MAX_FAILURES, Method, Verdict
from .otp import Otp, set_otp_secret
from .pin import Pin, set_pin
from .validate import ValidateOnly

METHODS: dict[str, type] = {"validate": ValidateOnly, "pin": Pin, "otp": Otp}


def get(name: str) -> Method:
    try:
        return METHODS[name]()
    except KeyError:
        raise BrokerError(f"unknown approval method {name!r} (choose from {', '.join(METHODS)})")


__all__ = ["MAX_FAILURES", "METHODS", "Method", "Verdict", "get", "set_pin", "set_otp_secret"]
