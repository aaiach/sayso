"""A secret the user supplies at approval time (SMS code, password, CVC, card number, expiry),
typed into the field the agent pointed at. One call = one secret = one approval."""
from __future__ import annotations

from ..approval import Approver
from ..browser import cdp, target as tg
from ..errors import BrokerError
from . import common, write

# what the user types -> policy kind, default field when the agent gives no target
WHAT = {
    "one-time code": ("otp", 'input[autocomplete="one-time-code"]'),
    "password": ("password", 'input[type="password"]'),
    "cvc": ("cvc", 'input[autocomplete="cc-csc"]'),
    "card_number": ("card", 'input[autocomplete="cc-number"]'),
    "expiry": ("card", 'input[autocomplete="cc-exp"]'),
}


async def locate(page, t: tg.Target, what: str):
    """(frame, field or [boxes], kind) for `what`, without touching anything."""
    if what not in WHAT:
        raise BrokerError(f"unknown secret {what!r} (choose from {', '.join(WHAT)})")
    kind, default = WHAT[what]
    if t.boxes:
        if what != "one-time code":
            raise BrokerError("boxes are only for one-time codes")
        frame, boxes = await tg.resolve_boxes(page, t, kind)
        return frame, boxes, kind
    frame, field = await tg.resolve(page, t, kind, default)
    return frame, field, kind


async def fill(page, approver: Approver, t: tg.Target, what: str, label: str) -> dict:
    frame, field, kind = await locate(page, t, what)
    req, ident = await common.request(page, frame, kind, label)
    if not common.approve(approver, req, ident):
        return {"status": "denied"}
    secret = approver.secret(req, what)
    try:
        if isinstance(field, list):
            r = await write.type_boxes(page, frame, field, secret, ident)
        else:
            r = await write.type_into(page, frame, field, secret, ident, click=not t.focused)
        n = len(secret)
    finally:
        secret = None
    # sites may reformat card numbers/expiry as you type ("4242 4242 …", "05 / 29")
    ok = r["length"] == n or what in ("card_number", "expiry") and r["length"] >= n
    return {"status": "filled" if r["filled"] and ok else "partial",
            "typed_length": r["length"], "expected_length": n, "frame": cdp.host(frame.url),
            **({"boxes": r["boxes"]} if "boxes" in r else {})}
