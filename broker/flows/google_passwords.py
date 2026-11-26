"""Password from Google Password Manager (synced into Chrome), filled by Chrome's own
autofill. Neither the broker nor the agent ever holds the password.

Steps: approve -> open Chrome's dropdown on the username (or password) field -> OCR entries,
find the account by username -> highlight -> Enter -> verify (masked). Nothing is submitted.
Two-step logins (email page, then password page): run once per step; on the first step only
the username is filled, on the second the password.
"""
from __future__ import annotations

import re

from ..approval import Approver
from ..browser import cdp, chrome_ui
from ..errors import BrokerError
from . import common, direct

MASK = re.compile(r"[•*·●]{3,}")
FOOTER = re.compile(r"manage|passwords?\b|use (an)?other|suggest|g[ée]rer|autre", re.I)


def account_entries(lines) -> list[dict]:
    """Account rows: a username line, usually followed by a masked-password line."""
    texts = [l.text for l in lines]
    titled = [t for i, t in enumerate(texts) if i + 1 < len(texts) and MASK.search(texts[i + 1])
              and not MASK.search(t)]
    if not titled:   # single-line rows
        titled = [t for t in texts if not MASK.search(t) and not FOOTER.search(t)]
    return [{"index": i, "label": t} for i, t in enumerate(titled)]


def find_entry(entries, username: str) -> int:
    u = username.lower()
    match = [e for e in entries if u in e["label"].lower().replace(" ", "")]
    if len(match) != 1:
        raise BrokerError(f"account {username} not uniquely found in dropdown")
    return match[0]["index"]


async def _optional(page, selector):
    try:
        return await cdp.find_field(page, selector, "password")
    except BrokerError:
        return None, None


async def _fields(page):
    """(frame, anchor field to open the dropdown on, password field or None, username field or None)."""
    pframe, pw = await _optional(page, direct.PASSWORD)
    uframe, user = await _optional(page, direct.USERNAME)
    # Anchor on the password field whenever it exists: on two-step pages Chrome treats the
    # email box as a username-only form, so picking the account there fills only the email.
    if pw is not None:
        return pframe, pw, pw, user
    if user is not None:
        return uframe, user, None, user
    raise BrokerError("no username or password field in an allowed frame")


async def select(page, username: str) -> list[dict]:
    _, anchor, pw, _ = await _fields(page)
    if pw is not None and (await cdp.masked(pw))["filled"]:
        raise BrokerError("password field already has a value")
    pop = await chrome_ui.open_dropdown(page, anchor)
    try:
        entries = account_entries(chrome_ui.dropdown_lines(pop, "password-dropdown.png"))
        chrome_ui.highlight(find_entry(entries, username))
        await page.wait_for_timeout(500)
    except Exception:
        chrome_ui.dismiss()
        raise
    return [{"index": e["index"]} for e in entries]


async def dry_run(page, username: str) -> dict:
    entries = await select(page, username)
    chrome_ui.dismiss()
    return {"status": "dry_run_ok", "entries": len(entries)}


async def fill(page, username: str, approver: Approver) -> dict:
    frame, _, pw, user = await _fields(page)
    req, ident = await common.request(page, frame, "password", username)
    if not common.approve(approver, req, ident):
        return {"status": "denied"}
    await common.before_write(page, ident)   # Chrome writes the password itself on Enter
    await select(page, username)
    if not chrome_ui.dropdown():
        return {"status": "dropdown_closed"}
    chrome_ui.accept()
    await page.wait_for_timeout(1500)
    out = {"username_filled": (await cdp.masked(user))["filled"] if user is not None else None,
           "password_field_present": pw is not None,
           "password_filled": (await cdp.masked(pw))["filled"] if pw is not None else False}
    done = out["password_filled"] or (pw is None and out["username_filled"])
    out["status"] = ("filled" if out["password_filled"] else "username_filled_next_step"
                     if done else "needs_user")
    return out
