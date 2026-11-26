"""Fills WITHOUT a password/card manager: the approver supplies the secret (terminal today,
the user's app later) and the broker types it with real keystrokes. Nothing is submitted.

Use cases: password (+ optional username), full card (number/expiry/CVC), CVC only.
One-time codes: flows/otp.py (same `type_into`).
"""
from __future__ import annotations

from ..approval import Approver
from ..browser import cdp, chrome_ui
from ..browser.identity import Identity
from ..desktop import x11
from ..errors import BrokerError
from . import common

PASSWORD = 'input[type="password"]'
USERNAME = ('input[autocomplete="username"], input[autocomplete="email"], input[type="email"], '
            'input[name*="user" i], input[name*="login" i], input[name*="email" i]')
CARD_NUMBER = 'input[autocomplete="cc-number"]'
CARD_EXPIRY = 'input[autocomplete="cc-exp"]'
CARD_CVC = 'input[autocomplete="cc-csc"]'


async def type_into(page, frame, locator, secret: str, ident: Identity) -> dict:
    """Atomic write: same site+certificate as approved, real click on an EMPTY field, confirm
    it has focus, type `secret` as real keystrokes. Returns masked facts."""
    if (await cdp.masked(locator))["filled"]:
        raise BrokerError("field already has a value")
    await common.before_write(page, ident)
    await chrome_ui.activate(page)
    await chrome_ui.real_click(page, locator)
    await page.wait_for_timeout(400)
    if chrome_ui.dropdown():          # Chrome may offer autofill on click: close it, keep focus
        chrome_ui.dismiss()
        await page.wait_for_timeout(200)
    if not await cdp.is_focused(frame, locator):
        raise BrokerError("field did not take focus")
    try:
        x11.type_secret(secret)
    finally:
        secret = None
    await page.wait_for_timeout(300)
    return await cdp.masked(locator)


async def fill_password(page, approver: Approver, username: str | None = None) -> dict:
    """Type a password supplied by the approver; also the username if given (not secret)."""
    frame, pw = await cdp.find_field(page, PASSWORD, "password")
    req, ident = await common.request(page, frame, "password", username or cdp.host(page.url))
    if not common.approve(approver, req, ident):
        return {"status": "denied"}
    secret = approver.secret(req, "password")
    try:
        out = {}
        if username:
            uframe, user = await cdp.find_field(page, USERNAME, "password")
            if not (await cdp.masked(user))["filled"]:
                out["username"] = await type_into(page, uframe, user, username, ident)
        out["password"] = await type_into(page, frame, pw, secret, ident)
    finally:
        secret = None
    return {"status": "filled" if out["password"]["filled"] else "failed", **out}


async def fill_card(page, approver: Approver, label: str = "card") -> dict:
    """Type card number, expiry and CVC supplied by the approver."""
    frame, number = await cdp.find_field(page, CARD_NUMBER, "card")
    req, ident = await common.request(page, frame, "card", label)
    if not common.approve(approver, req, ident):
        return {"status": "denied"}
    values = {w: approver.secret(req, w) for w in ("card_number", "expiry", "cvc")}
    try:
        out = {"number": await type_into(page, frame, number, values["card_number"].replace(" ", ""), ident)}
        for what, sel in (("expiry", CARD_EXPIRY), ("cvc", CARD_CVC)):
            f, loc = await cdp.find_field(page, sel, "card")
            out[what] = await type_into(page, f, loc, values[what], ident)
    finally:
        values = None
    return {"status": "filled" if all(v["filled"] for v in out.values()) else "failed",
            **{k: {"filled": v["filled"], "length": v["length"]} for k, v in out.items()}}


async def fill_cvc(page, approver: Approver, label: str = "card",
                   approved: tuple[Identity, str] | None = None) -> dict:
    """Type only the CVC (e.g. card already filled by a manager). A flow that already got
    approval and the CVC passes `approved=(identity, cvc)` instead of asking again."""
    frame, loc = await cdp.find_field(page, CARD_CVC, "cvc")
    if (await cdp.masked(loc))["filled"]:
        return {"status": "already_filled"}
    if approved:
        ident, secret = approved
    else:
        req, ident = await common.request(page, frame, "cvc", label)
        if not common.approve(approver, req, ident):
            return {"status": "denied"}
        secret = approver.secret(req, "cvc")
    try:
        r = await type_into(page, frame, loc, secret, ident)
    finally:
        secret = approved = None
    return {"status": "filled" if r["filled"] else "failed", "cvc_length": r["length"]}
