"""One-time codes (SMS / email / authenticator) typed by the broker: finds the code input
(one field, or N single-character boxes), gets the code from the approver, types it. Nothing
is submitted."""
from __future__ import annotations

from ..approval import Approver
from ..browser import cdp
from ..errors import BrokerError
from . import common, direct

OTP_SELECTORS = (
    'input[autocomplete="one-time-code"]',
    'input[name*="otp" i], input[id*="otp" i], input[name*="code" i], input[id*="code" i]',
    'input[inputmode="numeric"]',
)


_SIBLING_SELECTOR_JS = """e => {
    const prefix = (e.name || '').replace(/\\d+$/, '');
    if (prefix && prefix !== e.name) return `input[name^="${prefix}"]`;
    return e.form ? 'form input[maxlength="1"]' : 'input[maxlength="1"]'; }"""


async def find_boxes(page):
    """(frame, [locators]) of the code input: one field, or N single-character boxes."""
    for sel in OTP_SELECTORS:
        try:
            frame, first = await cdp.find_field(page, sel, "otp")
        except BrokerError:
            continue
        loc = frame.locator(sel)
        boxes = [loc.nth(i) for i in range(await loc.count()) if await loc.nth(i).is_visible()]
        # Split codes: often only box 1 is tagged one-time-code; siblings share a name prefix
        # (token-input-1..6) or are maxlength=1 inputs in the same form.
        siblings = frame.locator(await first.evaluate(_SIBLING_SELECTOR_JS))
        sib = [siblings.nth(i) for i in range(await siblings.count()) if await siblings.nth(i).is_visible()]
        return frame, sib if len(sib) > len(boxes) else boxes
    raise BrokerError("no one-time-code field found")


async def fill_otp(page, approver: Approver, label: str = "one-time code") -> dict:
    """Type a one-time code supplied by the approver. Multi-box inputs: typing into the first
    box (sites auto-advance). Nothing is submitted."""
    frame, boxes = await find_boxes(page)
    if any([(await cdp.masked(b))["filled"] for b in boxes]):
        raise BrokerError("code field already has a value")
    req, ident = await common.request(page, frame, "otp", label,
                                      (("one-time code", await common.length_hint(boxes)),))
    if not common.approve(approver, req, ident):
        return {"status": "denied"}
    secret = approver.secret(req, "one-time code")
    try:
        await direct.type_into(page, frame, boxes[0], secret, ident)
        n = len(secret)
    finally:
        secret = None
    typed = sum([(await cdp.masked(b))["length"] for b in boxes])
    return {"status": "filled" if typed == n else "partial", "boxes": len(boxes),
            "characters_in_fields": typed, "characters_expected": n}
