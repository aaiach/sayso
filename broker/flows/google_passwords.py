"""Password from Google Password Manager (synced into Chrome), filled by Chrome's own
autofill. Neither the broker nor the agent ever holds the password.

Steps: approve -> open Chrome's dropdown on the username (or password) field -> OCR entries,
find the account by username -> highlight -> Enter -> verify (masked). Nothing is submitted.
Two-step logins (email page, then password page): run once per step; on the first step only
the username is filled, on the second the password.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from ..approval import Approver
from ..browser import cdp, chrome_ui, target as tg
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


def _score(username: str, label: str) -> float:
    """How well an OCR'd dropdown row matches the username: 1.0 = contained exactly; else the
    best similarity against any word (OCR misreads like '.corn' for '.com' still score high)."""
    u, lab = username.lower(), label.lower()
    if u in lab.replace(" ", ""):
        return 1.0
    return max([SequenceMatcher(None, u, w).ratio() for w in lab.split()] + [0.0])


def find_entry(entries, username: str) -> int:
    """The one row for `username`: an exact hit, or one clearly best near-match (>= 0.85 and
    0.1 ahead of the next). Otherwise refuse, listing the account names seen (no passwords)."""
    ranked = sorted(((_score(username, e["label"]), e) for e in entries), key=lambda x: -x[0])
    best = ranked[0][0] if ranked else 0.0
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    if best >= 0.85 and (best == 1.0 and second < 1.0 or best - second >= 0.1):
        return ranked[0][1]["index"]
    seen = ", ".join(e["label"] for e in entries) or "no entries"
    raise BrokerError(f"account {username} not uniquely found in Chrome's list; it shows: {seen}")


async def _optional(page, selector):
    try:
        return await cdp.find_field(page, selector, "password")
    except BrokerError:
        return None, None


ANCHOR_TYPES = {"password", "email", "text", ""}


async def locate(page, t: tg.Target | None = None):
    """(frame, anchor field to open the dropdown on, password field or None, username field or None).
    With a target from the agent, the anchor is that field."""
    if t is not None and t.given:
        frame, anchor = await tg.resolve(page, t, "password", direct.PASSWORD, ANCHOR_TYPES)
        pw = anchor if (await tg.facts(anchor))["type"] == "password" else (await _optional(page, direct.PASSWORD))[1]
        return frame, anchor, pw, (await _optional(page, direct.USERNAME))[1]
    pframe, pw = await _optional(page, direct.PASSWORD)
    uframe, user = await _optional(page, direct.USERNAME)
    # Anchor on the password field whenever it exists: on two-step pages Chrome treats the
    # email box as a username-only form, so picking the account there fills only the email.
    if pw is not None:
        return pframe, pw, pw, user
    if user is not None:
        return uframe, user, None, user
    raise BrokerError("no username or password field in an allowed frame")


async def select(page, username: str, t: tg.Target | None = None) -> list[dict]:
    _, anchor, pw, _ = await locate(page, t)
    if pw is not None and (await cdp.masked(pw))["filled"]:
        raise BrokerError("password field already has a value")
    pop = await chrome_ui.open_dropdown(page, anchor)
    try:
        entries = account_entries(chrome_ui.dropdown_lines(pop))
        chrome_ui.highlight(find_entry(entries, username))
        await page.wait_for_timeout(500)
    except Exception:
        chrome_ui.dismiss()
        raise
    return [{"index": e["index"]} for e in entries]


async def dry_run(page, username: str, t: tg.Target | None = None) -> dict:
    entries = await select(page, username, t)
    chrome_ui.dismiss()
    return {"status": "dry_run_ok", "entries": len(entries)}


async def fill(page, username: str, approver: Approver, t: tg.Target | None = None) -> dict:
    frame, _, pw, user = await locate(page, t)
    req, ident = await common.request(page, frame, "password", username)
    if not common.approve(approver, req, ident):
        return {"status": "denied"}
    await common.before_write(page, ident)   # Chrome writes the password itself on Enter
    await select(page, username, t)
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
