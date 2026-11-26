"""What the user is asked to approve (never secret), and how typed secrets are normalised."""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..errors import BrokerError


@dataclass(frozen=True)
class Request:
    kind: str                 # "card" | "cvc" | "password" | "otp"
    site: str                 # top-level host, from CDP
    frame: str                # frame host the secret goes into
    label: str                # e.g. "My Visa ••4242" or "user@example.com"
    amount: str | None = None
    certificate: str = ""     # "<subject> by <issuer>, sha256 <fp…>" as Chrome sees it
    warnings: tuple[str, ...] = ()   # from trust_store (first visit, new cert, other issuer)
    asks: tuple[tuple[str, int | None], ...] = ()   # secrets the user types: (what, length hint)


# AZERTY (fr / fr-mac) top row without Shift -> digits, so numeric codes can be typed either way.
AZERTY_DIGITS = str.maketrans("&é\"'(§-è_!çà", "123456678890")

# What each secret looks like; used to reject typos before anything is typed.
SECRET_FORMATS = {
    "cvc": re.compile(r"\d{3,4}"),
    "card_number": re.compile(r"\d{12,19}"),
    "expiry": re.compile(r"(0[1-9]|1[0-2])/?\d{2}"),
    "password": re.compile(r".+"),
    "one-time code": re.compile(r"[0-9A-Za-z]{4,10}"),
}

NUMERIC = ("one-time code", "cvc", "card_number", "expiry")


def digits(value: str) -> str:
    """Numeric entry typed on AZERTY without Shift still counts; spaces, dashes, dots dropped."""
    value = value.strip()
    if not re.search(r"\d", value):
        value = value.translate(AZERTY_DIGITS)
    return re.sub(r"[\s\-.]", "", value)


def normalise(what: str, value: str) -> str:
    value = value.strip()
    if what == "expiry":
        value = re.sub(r"[\s.]", "", value.translate(AZERTY_DIGITS) if not re.search(r"\d", value) else value)
    elif what in NUMERIC:
        value = digits(value)
    fmt = SECRET_FORMATS.get(what)
    if fmt and not fmt.fullmatch(value):
        raise BrokerError(f"{what} has the wrong format (expected e.g. 6 digits)")
    return value
