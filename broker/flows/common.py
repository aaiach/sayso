"""Shared steps of every flow: build the approval request (with the site's identity and
fingerprint warnings), record approved fingerprints, and re-verify right before writing."""
from __future__ import annotations

from .. import trust_store
from ..approval import Approver, Request
from ..browser import cdp, identity


async def request(page, frame, kind: str, label: str) -> tuple[Request, identity.Identity]:
    ident = await identity.read(page)
    req = Request(kind, ident.host, cdp.host(frame.url), label, await cdp.detect_amount(page),
                  f"{ident.subject} by {ident.issuer}, sha256 {ident.sha256[:16]}…",
                  trust_store.warnings(ident))
    return req, ident


def approve(approver: Approver, req: Request, ident: identity.Identity) -> bool:
    if not approver.approve(req):
        return False
    trust_store.remember(ident)
    return True


async def before_write(page, ident: identity.Identity) -> None:
    """Same site and certificate as approved; raises otherwise."""
    await identity.verify_unchanged(page, ident)
