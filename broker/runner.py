"""Runs one FillSpec end to end in the approval window, and writes only the masked result.

  python -m broker.runner <spec.json> <result.json> [deadline_epoch]

The spec file is deleted as soon as it's read; the result file (0600) holds a status and
masked facts, never a value. Errors are reported by type unless they are BrokerErrors.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

from . import spec as sp
from .approval import Approver, TerminalApprover
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


def _write(path: str, out: dict) -> None:
    fd = os.open(path + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(out, f)
    os.replace(path + ".tmp", path)


def main(spec_path: str, result_path: str, deadline: str = "") -> None:
    started = time.time()
    try:
        with open(spec_path) as f:
            raw = json.load(f)
        os.unlink(spec_path)
        s = sp.parse(raw)
        print(f"sayso: {s.secret['from']} on {s.site} ({sp.label(s)})")
        approver = Expiring(TerminalApprover(s.approval), float(deadline or started + 170))
        out = asyncio.run(run(s, approver))
    except BrokerError as e:
        out = {"status": "refused", "reason": str(e)}
    except KeyboardInterrupt:
        out = {"status": "denied", "reason": "window interrupted"}
    except Exception as e:  # secrets may be in scope: never print exception details
        out = {"status": "error", "reason": masked(e)}
    out["seconds"] = round(time.time() - started, 1)
    _write(result_path, out)
    print(f"\nResult: {out['status']}" + (f" ({out['reason']})" if out.get("reason") else ""))
    print("Nothing was submitted. This window closes in 3 s.")
    time.sleep(3)


if __name__ == "__main__":
    main(*sys.argv[1:4])
