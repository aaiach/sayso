"""Secrets saved in Chrome (Google Password Manager passwords, Google Pay cards): approval only.

The broker checks the site and the field the agent points at, and asks the user. It fills
nothing: the agent then opens Chrome's autofill on that field and picks the approved entry
itself. Chrome-saved secrets live in the profile the agent drives, so the broker could not
lock them away anyway; the approval is the user's explicit go-ahead, on record.
"""
from __future__ import annotations

from ..approval import Approver
from ..browser import cdp, target as tg
from . import common

PASSWORD = 'input[type="password"]'
CARD_NUMBER = 'input[autocomplete="cc-number"]'
ANCHOR_TYPES = {"password", "email", "text", ""}     # password step or username step


async def locate(page, t: tg.Target, source: str):
    """(frame, field, kind): the field the agent will open Chrome's autofill on."""
    if source == "google_password":
        frame, field = await tg.resolve(page, t, "password", PASSWORD, ANCHOR_TYPES)
        return frame, field, "password"
    frame, field = await tg.resolve(page, t, "card", CARD_NUMBER)
    return frame, field, "card"


def entry(secret: dict) -> str:
    """The entry the user approves, as it appears in Chrome's list."""
    if secret["from"] == "google_password":
        return f"saved password for {secret['username']}"
    return f"{secret['card']} ••{secret['last4']}"


async def approve(page, approver: Approver, t: tg.Target, secret: dict) -> dict:
    frame, field, kind = await locate(page, t, secret["from"])
    req, ident = await common.request(page, frame, kind, entry(secret))
    if not common.approve(approver, req, ident):
        return {"status": "denied"}
    return {"status": "approved", "entry": entry(secret), "frame": cdp.host(frame.url),
            "next": "open Chrome's autofill on this field and pick exactly this entry; "
                    "nothing was filled by the broker"}
