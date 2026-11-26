"""Card from the user's Google account (Google Pay cards synced into Chrome), filled by
Chrome's own autofill. Neither the broker nor the agent ever holds the card number.

Steps: approve (+ collect CVC up front, before focus moves) -> open Chrome's dropdown on the
card field -> OCR entries, find the card by last 4 -> highlight -> Enter -> if Chrome shows
its unmask prompt, type the CVC there (only if the prompt owns the keyboard) -> verify masked
-> if the merchant CVC box is still empty, type the CVC there. Nothing is submitted.
"""
from __future__ import annotations

import re

from ..approval import Approver
from ..browser import cdp, chrome_ui, target as tg
from ..desktop import x11
from ..errors import BrokerError
from . import common, direct

ROW = re.compile(r"(\d{4})\s*\S?\s*\d{2}/\d{2}")   # "••4242 • 05/29"


def card_entries(lines) -> list[dict]:
    """Card rows in Chrome's dropdown: each has one '<last4> • MM/YY' line, title above it."""
    out, prev = [], ""
    for line in lines:
        m = ROW.search(line.text)
        if m:
            out.append({"index": len(out), "last4": m.group(1), "label": f"{prev} {line.text}"})
        prev = line.text
    return out


def find_entry(entries, card: str, last4: str) -> int:
    word = card.lower().split()[0]
    match = [e for e in entries if e["last4"] == last4 and word in e["label"].lower()]
    if len(match) != 1:                       # OCR titles are noisy: last 4 alone if unique
        match = [e for e in entries if e["last4"] == last4]
    if len(match) != 1:
        raise BrokerError(f"card ••{last4} not uniquely found in dropdown")
    return match[0]["index"]


async def locate(page, t: tg.Target | None):
    """(frame, card-number field): the agent's target, else the standard cc-number field."""
    return await tg.resolve(page, t or tg.Target(), "card", direct.CARD_NUMBER)


async def select(page, card: str, last4: str, t: tg.Target | None = None) -> list[dict]:
    """Open the dropdown and highlight the card (preview only). Returns masked entries."""
    _, field = await locate(page, t)
    if (await cdp.masked(field))["filled"]:
        raise BrokerError("card field already has a value")
    pop = await chrome_ui.open_dropdown(page, field)
    try:
        entries = card_entries(chrome_ui.dropdown_lines(pop))
        chrome_ui.highlight(find_entry(entries, card, last4))
        await page.wait_for_timeout(500)
        if (await cdp.masked(field))["filled"]:
            raise BrokerError("value committed during highlight (unexpected)")
    except Exception:
        chrome_ui.dismiss()
        raise
    return [{"index": e["index"], "last4": e["last4"]} for e in entries]


async def dry_run(page, card: str, last4: str, t: tg.Target | None = None) -> dict:
    entries = await select(page, card, last4, t)
    chrome_ui.dismiss()
    return {"status": "dry_run_ok", "entries": entries}


async def _commit_and_unmask(page, frame, field, cvc: str | None, ident) -> dict:
    if not chrome_ui.dropdown():              # never press Enter on the bare page
        return {"status": "dropdown_closed"}
    before = chrome_ui.snapshot()
    if not chrome_ui.dropdown():
        return {"status": "dropdown_closed"}
    chrome_ui.accept()
    await page.wait_for_timeout(2500)

    prompt = False
    for _ in range(4):
        if (await cdp.masked(field))["filled"]:
            break
        if chrome_ui.unmask_prompt_shown(before):
            prompt = True
            break
        await page.wait_for_timeout(1000)

    typed = False
    if prompt and cvc:
        if not await chrome_ui.prompt_has_keyboard(page):
            return {"status": "needs_user", "reason": "cvc_prompt_not_confirmed"}
        await common.before_write(page, ident)
        if not await chrome_ui.prompt_has_keyboard(page):   # recheck after the CDP round-trip
            return {"status": "needs_user", "reason": "cvc_prompt_not_confirmed"}
        x11.type_secret(cvc)
        x11.key("Return")
        typed = True
        for _ in range(20):
            await page.wait_for_timeout(1000)
            if (await cdp.masked(field))["filled"]:
                break
    elif prompt:
        return {"status": "needs_user", "reason": "cvc_prompt_shown_no_cvc"}
    await page.wait_for_timeout(1000)
    return {"cvc_prompt_detected": prompt, "broker_typed_cvc_in_prompt": typed}


async def fill(page, card: str, last4: str, approver: Approver, t: tg.Target | None = None) -> dict:
    frame, field = await locate(page, t)
    if (await cdp.masked(field))["filled"]:
        raise BrokerError("card field already has a value")
    req, ident = await common.request(page, frame, "card", f"{card} ••{last4}")
    if not common.approve(approver, req, ident):
        return {"status": "denied"}
    cvc = approver.secret(req, "cvc", optional=True)      # before focus moves to Chrome
    try:
        await common.before_write(page, ident)   # Chrome writes the card itself on Enter
        await select(page, card, last4, t)
        out = await _commit_and_unmask(page, frame, field, cvc, ident)
        if out.get("status"):
            return out
        num = await cdp.masked(field, last4=True)
        out.update(status="filled" if num["last4"] == last4 else "failed",
                   number_digits=num["digits"], last4_matches=num["last4"] == last4)
        for what, sel in (("expiry", direct.CARD_EXPIRY), ("cvc", direct.CARD_CVC)):
            try:
                _, loc = await cdp.find_field(page, sel, "card")
                out[f"{what}_filled"] = (await cdp.masked(loc))["filled"]
            except BrokerError:
                pass
        if out["status"] == "filled" and cvc and out.get("cvc_filled") is False:
            out["merchant_cvc"] = await direct.fill_cvc(page, approver, req.label, approved=(ident, cvc))
        return out
    finally:
        cvc = None
