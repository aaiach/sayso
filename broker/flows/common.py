"""Shared steps of every flow: build the approval request (with the site's identity and
fingerprint warnings), record approved fingerprints, and re-verify right before writing."""
from __future__ import annotations

from .. import trust_store
from ..approval import Approver, Request
from ..browser import cdp, identity


async def request(page, frame, kind: str, label: str, asks: tuple = ()) -> tuple[Request, identity.Identity]:
    """`asks`: the secrets the user will type when approving, as (what, length hint or None)."""
    ident = await identity.read(page)
    req = Request(kind, ident.host, cdp.host(frame.url), label, await cdp.detect_amount(page),
                  f"{ident.subject} by {ident.issuer}, sha256 {ident.sha256[:16]}…",
                  trust_store.warnings(ident), asks)
    return req, ident


async def length_hint(field) -> int | None:
    """How many characters the page expects: the number of split boxes, or the field's
    maxlength when it looks like a code length. Only a hint for the phone's input."""
    if isinstance(field, list):
        return len(field) if len(field) > 1 else await length_hint(field[0]) if field else None
    if field is None:
        return None
    m = await field.get_attribute("maxlength")
    return int(m) if m and m.isdigit() and 3 <= int(m) <= 10 else None


def approve(approver: Approver, req: Request, ident: identity.Identity) -> bool:
    if not approver.approve(req):
        return False
    trust_store.remember(ident)
    return True


async def before_write(page, ident: identity.Identity) -> None:
    """Same site and certificate as approved; raises otherwise."""
    await identity.verify_unchanged(page, ident)
