"""Web-page inspection over CDP (Playwright). Works for any Chromium page; no Chrome-UI or
password-manager knowledge. Never used to *write* secrets: Playwright's fill/type echo
their arguments in errors. Reads are masked (lengths, last 4, filled or not).
"""
from __future__ import annotations

import os
import re
import subprocess

from .. import config, policy
from ..errors import BrokerError

CDP_URL, PROFILE = config.CDP_URL, config.PROFILE


def host(url: str) -> str:
    return url.split("/")[2] if "://" in url else ""


def browser_pid() -> str:
    """Main process of the browser running PROFILE (the one without --type=)."""
    if not PROFILE:
        raise BrokerError("set BROKER_PROFILE in .env (the browser's --user-data-dir)")
    out = subprocess.run(["pgrep", "-f", f"user-data-dir={PROFILE}"], capture_output=True, text=True).stdout
    for p in out.split():
        try:
            if "--type=" not in open(f"/proc/{p}/cmdline").read():
                return p
        except FileNotFoundError:
            pass
    raise BrokerError("browser not running")


async def find_page(browser, site: str):
    pages = [p for c in browser.contexts for p in c.pages if host(p.url) == site]
    if not pages:
        raise BrokerError(f"no open tab on {site}")
    return pages[-1]


async def find_field(page, selector: str, kind: str):
    """(frame, locator) of the first visible `selector` in a frame allowed for `kind`
    (policy: site's own/same-domain frame for passwords, payment providers for cards)."""
    site = host(page.url)
    for frame in page.frames:
        if not policy.frame_allowed(site, frame.url, kind):
            continue
        loc = frame.locator(selector)
        if await loc.count() and await loc.first.is_visible():
            policy.check(site, frame.url, kind)
            return frame, loc.first
    raise BrokerError(f"no {selector} field in an allowed frame on {site}")


async def box(locator) -> dict:
    """Page-viewport box of an element (Playwright boxes are relative to the main frame)."""
    b = await locator.bounding_box()
    if not b:
        raise BrokerError("field not visible")
    return b


async def to_screen(page, x: float, y: float) -> tuple[int, int]:
    """Viewport point -> screen point (browser toolbars sit above the content)."""
    g = await page.evaluate("() => ({sx: screenX, sy: screenY, ow: outerWidth, oh: outerHeight,"
                            " iw: innerWidth, ih: innerHeight, dpr: devicePixelRatio})")
    border = (g["ow"] - g["iw"]) / 2
    return (int(g["sx"] + border + x * g["dpr"]),
            int(g["sy"] + (g["oh"] - g["ih"]) - border + y * g["dpr"]))


async def masked(locator, last4: bool = False) -> dict:
    """Masked facts about a field's value. Never returns the value."""
    v = await locator.input_value()
    out = {"filled": bool(v), "length": len(v)}
    if last4:
        d = re.sub(r"\D", "", v)
        out.update(digits=len(d), last4=d[-4:] if len(d) >= 12 else "")
    del v
    return out


async def detect_amount(page) -> str | None:
    try:
        txt = await page.inner_text("body")
    except Exception:
        return None
    m = re.search(r"(?:Total|TOTAL)[^\d€$£]{0,40}([\d.,]+\s?[€$£]|[€$£]\s?[\d.,]+)", txt)
    return m.group(1) if m else None
