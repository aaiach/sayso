"""Runs one FillSpec end to end with a given approver (phone or local) and returns only a
status and masked facts, never a value. Errors are reported by type unless they are
BrokerErrors (secrets may be in scope).
"""
from __future__ import annotations

import time

from . import spec as sp
from .approval import Approver
from .browser import cdp, identity
from .errors import BrokerError, masked
from .flows import saved, user_secret


class Expiring:
    """Approver wrapper: an answer that arrives after the deadline counts for nothing (the
    agent has already been told the request timed out)."""

    def __init__(self, inner: Approver, deadline: float):
        self.inner, self.deadline = inner, deadline

    def _check(self) -> None:
        if time.time() > self.deadline:
            raise BrokerError("answer came after the request expired")

    def approve(self, req) -> bool:
        ok = self.inner.approve(req)
        self._check()
        return ok

    def secret(self, req, what: str, optional: bool = False):
        value = self.inner.secret(req, what, optional)
        self._check()
        return value


async def run(s: sp.FillSpec, approver: Approver) -> dict:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        page = await cdp.find_page(await p.chromium.connect_over_cdp(cdp.CDP_URL), s.site)
        ident = await identity.read(page)                 # HTTPS + secure, before any UI
        if ident.host != s.site:
            raise BrokerError(f"tab is on {ident.host}, not {s.site}")
        sec, t = s.secret, s.tgt
        if sec["from"] in ("google_password", "google_card"):
            return await saved.approve(page, approver, t, sec)
        return await user_secret.fill(page, approver, t, sec["what"], sp.label(s))


async def execute(s: sp.FillSpec, approver: Approver) -> dict:
    """run(), with errors turned into a status: BrokerError reasons are shown, anything else
    only by type (secrets may be in scope)."""
    try:
        return await run(s, approver)
    except BrokerError as e:
        return {"status": "refused", "reason": str(e)}
    except Exception as e:
        return {"status": "error", "reason": masked(e)}
