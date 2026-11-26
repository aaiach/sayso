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


async def blur_all(page) -> None:
    for f in page.frames:
        try:
            await f.evaluate("() => document.activeElement && document.activeElement.blur()")
        except Exception:
            pass


_INERT_JS = """([x, y, w, h]) => {
    const bad = 'a,button,input,select,textarea,label,iframe,[role],[onclick],[tabindex],summary';
    const cands = [[x + w/2, y - 70], [x + w/2, y - 110], [x + w + 40, y + h/2], [x - 40, y + h/2],
                   [x + w/2, y + h + 140], [x + w + 200, y + h/2], [x - 200, y + h/2], [20, 20]];
    const out = [];
    for (const [cx, cy] of cands) {
        if (cx < 0 || cy < 0 || cx > innerWidth || cy > innerHeight) continue;
        const el = document.elementFromPoint(cx, cy);
        if (el && !el.closest(bad) && getComputedStyle(el).cursor !== 'pointer') out.push([cx, cy]);
    }
    return out; }"""


async def inert_points_near(page, b: dict) -> list[tuple[float, float]]:
    """Viewport points near box `b` verified to be non-interactive (safe to click), best first."""
    return await page.evaluate(_INERT_JS, [b["x"], b["y"], b["width"], b["height"]])


_EDITABLE_FOCUSED_JS = """() => { const e = document.activeElement;
    return !!(document.hasFocus() && e && (e.tagName === 'INPUT' || e.tagName === 'TEXTAREA'
              || e.tagName === 'SELECT' || e.isContentEditable)); }"""


async def editable_focused(page) -> bool:
    """True if keystrokes would land in a page field (any frame). Unreadable frames count
    as focused. (document.hasFocus() alone stays true under Chrome's own prompts.)"""
    for f in page.frames:
        try:
            if await f.evaluate(_EDITABLE_FOCUSED_JS):
                return True
        except Exception:
            if not f.is_detached() and f.url.startswith("http"):
                return True
    return False


async def is_focused(frame, locator) -> bool:
    """True if `locator` is the focused element of a focused frame."""
    return await locator.evaluate("e => document.hasFocus() && document.activeElement === e")


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
