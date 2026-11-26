"""The last step of every fill: put a secret into a checked field as real keystrokes.
Same site and certificate as approved, empty field, real focus, then type. Returns masked facts."""
from __future__ import annotations

from ..browser import cdp, chrome_ui, focus
from ..browser.identity import Identity
from ..desktop import x11
from ..errors import BrokerError
from . import common


async def _focus(page, frame, locator, click: bool) -> None:
    """Give `locator` real keyboard focus. click=False: the agent focused it already
    (custom widgets); only bring the window forward and confirm."""
    await chrome_ui.activate(page)
    if click:
        await chrome_ui.real_click(page, locator)
        await page.wait_for_timeout(400)
        if chrome_ui.dropdown():          # Chrome may offer autofill on click: close it, keep focus
            chrome_ui.dismiss()
            await page.wait_for_timeout(200)
    if not await focus.is_focused(frame, locator):
        raise BrokerError("field did not take focus" if click else "target is no longer focused")


async def type_into(page, frame, locator, secret: str, ident: Identity, click: bool = True) -> dict:
    """One field, the whole secret."""
    if (await cdp.masked(locator))["filled"]:
        raise BrokerError("field already has a value")
    await common.before_write(page, ident)
    await _focus(page, frame, locator, click)
    try:
        x11.type_secret(secret)
    finally:
        secret = None
    await page.wait_for_timeout(300)
    return await cdp.masked(locator)


async def type_boxes(page, frame, boxes: list, secret: str, ident: Identity) -> dict:
    """One character per box (split code inputs). Works whether or not the site moves focus
    to the next box by itself: each box is checked, and clicked only if it lacks focus."""
    if len(boxes) < len(secret):
        raise BrokerError(f"{len(boxes)} boxes for a {len(secret)}-character secret")
    if any([(await cdp.masked(b))["filled"] for b in boxes]):
        raise BrokerError("code boxes already have a value")
    await common.before_write(page, ident)
    n = len(secret)
    try:
        for i, ch in enumerate(secret):
            await _focus(page, frame, boxes[i], click=not await focus.is_focused(frame, boxes[i]))
            x11.type_secret(ch)
            await page.wait_for_timeout(150)
    finally:
        secret = ch = None
    lengths = [(await cdp.masked(b))["length"] for b in boxes]
    return {"filled": all(x == 1 for x in lengths[:n]), "length": sum(lengths), "boxes": len(boxes)}


async def type_in_chrome_prompt(page, secret: str, ident: Identity) -> dict:
    """Chrome's own CVC prompt, which the agent has just seen open. Typed only if Chrome is the
    active window and nothing in the page has focus (so neither the digits nor the Enter can
    reach the page), then confirmed with Enter."""
    await common.before_write(page, ident)
    x11.activate(x11.main_window(cdp.browser_pid()))   # the approval window had the keyboard
    await page.wait_for_timeout(500)
    if not await chrome_ui.prompt_has_keyboard(page):
        raise BrokerError("Chrome's prompt does not have the keyboard (Chrome not active, or "
                          "something in the page has focus)")
    n = len(secret)
    try:
        x11.type_secret(secret)
    finally:
        secret = None
    x11.key("Return")
    await page.wait_for_timeout(1500)
    return {"filled": True, "length": n}
