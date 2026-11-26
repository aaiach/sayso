"""Dry run for the agent: what the broker sees at a target, without approval, clicks or
secrets. Lets the agent iterate on a difficult page before asking the user anything."""
from __future__ import annotations

from . import spec as sp, trust_store
from .browser import cdp, identity, target as tg
from .errors import BrokerError
from .flows import google_cards, google_passwords, user_secret


async def _field_facts(frame, loc) -> dict:
    f = await tg.facts(loc)
    m = await cdp.masked(loc)
    return {"frame": cdp.host(frame.url), "tag": f["tag"].lower(), "type": f["type"] or "text",
            "name": f["name"], "id": f["id"], "autocomplete": f["autocomplete"], "empty": not m["filled"]}


async def check(s: sp.FillSpec) -> dict:
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp.CDP_URL)
        page = await cdp.find_page(browser, s.site)
        tabs = sum(1 for c in browser.contexts for pg in c.pages if cdp.host(pg.url) == s.site)
        ident = await identity.read(page)
        if ident.host != s.site:
            raise BrokerError(f"tab is on {ident.host}, not {s.site}")
        out = {"status": "ok", "tabs_on_site": tabs,
               "site": {"host": ident.host, "issuer": ident.issuer, "sha256": ident.sha256[:16],
                        "warnings": list(trust_store.warnings(ident))}}
        src, t = s.secret["from"], s.tgt
        if src == "google_password":
            frame, anchor, pw, user = await google_passwords.locate(page, t)
            out["anchor"] = await _field_facts(frame, anchor)
            out["password_field_present"] = pw is not None
        elif src == "google_card":
            frame, field = await google_cards.locate(page, t)
            out["field"] = await _field_facts(frame, field)
        else:
            frame, field, _ = await user_secret.locate(page, t, s.secret["what"])
            if isinstance(field, list):
                out["boxes"] = [await _field_facts(frame, b) for b in field]
            else:
                out["field"] = await _field_facts(frame, field)
        return out
