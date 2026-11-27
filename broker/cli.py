"""User-run CLI, one subcommand per use case. Dry run unless --fill. Nothing is ever submitted.

  python -m broker.cli card            --site shop.example.com [--label "My Visa"] --fill
  python -m broker.cli cvc             --site shop.example.com [--label "My Visa ••4242"] --fill
  python -m broker.cli password        --site app.example.com [--username user@example.com] --fill
  python -m broker.cli otp             --site bank.example.com [--label "Bank SMS code"] --fill

Each fill asks for approval on the paired phone or on this computer (see channel.py), like the
MCP tool. One-time setup, run directly in a terminal: setup (secret store check + phone
pairing), pair, unpair.

Prints one JSON line of masked results. Errors print their type only when unexpected.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from . import trust_store
from . import setup_wizard
from .browser import cdp, identity
from .errors import BrokerError, masked
from .flows import direct, otp


def _args():
    ap = argparse.ArgumentParser(prog="broker")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("card", "cvc", "password", "otp"):
        p = sub.add_parser(name)
        p.add_argument("--site", required=True, help="top-level host of the open tab")
        p.add_argument("--fill", action="store_true", help="really fill (default: dry run)")
        if name == "password":
            p.add_argument("--username")
        if name in ("card", "cvc", "otp"):
            p.add_argument("--label", default="card")
    sub.add_parser("setup")
    sub.add_parser("pair")
    sub.add_parser("unpair")
    return ap.parse_args()


def _unpair() -> dict:
    from .phone import keys
    keys.forget_device()
    return {"status": "unpaired"}


def _pair() -> dict:
    from .phone import pair
    return pair.pair()


SETUP = {"setup": setup_wizard.run, "pair": _pair, "unpair": _unpair}


async def _run(a) -> dict:
    if a.cmd in SETUP:
        return SETUP[a.cmd]()
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        page = await cdp.find_page(await p.chromium.connect_over_cdp(cdp.CDP_URL), a.site)
        if not a.fill:
            ident = await identity.read(page)          # refuse insecure sites before any UI
            out = await _dry(page, a)
            out["site"] = {"chrome": ident.security_state, "subject": ident.subject, "issuer": ident.issuer,
                           "sha256": ident.sha256[:16], "warnings": list(trust_store.warnings(ident))}
            return out
        approver = _approver()
        if a.cmd == "card":
            return await direct.fill_card(page, approver, a.label)
        if a.cmd == "cvc":
            return await direct.fill_cvc(page, approver, a.label)
        if a.cmd == "otp":
            return await otp.fill_otp(page, approver, a.label)
        return await direct.fill_password(page, approver, a.username)


def _approver():
    import time
    from . import channel, runner
    deadline = time.time() + 170
    return runner.Expiring(channel.approver(channel.which(), deadline), deadline)


async def _dry(page, a) -> dict:
    """Dry runs: everything up to (not including) committing a value."""
    if a.cmd == "otp":
        frame, boxes = await otp.find_boxes(page)
        return {"status": "dry_run_ok", "frame": cdp.host(frame.url), "boxes": len(boxes)}
    sel = {"card": direct.CARD_NUMBER, "cvc": direct.CARD_CVC, "password": direct.PASSWORD}[a.cmd]
    frame, loc = await cdp.find_field(page, sel, a.cmd)
    return {"status": "dry_run_ok", "frame": cdp.host(frame.url), "field": sel,
            "empty": not (await cdp.masked(loc))["filled"]}


def main():
    a = _args()
    try:
        out = asyncio.run(_run(a))
    except BrokerError as e:
        sys.exit(f"FAIL: {e}")
    except Exception as e:  # secrets may be in scope: never print exception details
        sys.exit(f"FAIL: {masked(e)}")
    print(json.dumps(out))
    if getattr(a, "fill", False):
        print("Nothing was submitted. Review the page before continuing.")


if __name__ == "__main__":
    main()
