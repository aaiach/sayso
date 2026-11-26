"""Chrome's own UI, outside the web page: the autofill dropdown (cards, passwords,
addresses) and the card unmask ("Enter the CVC") prompt. Chrome-specific; knows nothing
about where the saved data comes from (Google Pay, Google Password Manager, ...).

Chrome ignores CDP-synthesised input for its autofill UI after earlier attempts, so all
interaction is real X11 input via desktop.x11. Chrome's accessibility tree is nearly empty,
so its UI is read by screenshots + OCR.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..desktop import ocr, x11
from ..errors import BrokerError
from . import cdp

# Words in Chrome's unmask prompt ("Enter the CVC for Visa ••••1234", "Confirm card", ...).
UNMASK_WORDS = re.compile(r"\b(cvc|cvv|security code|code de s[ée]curit[ée]|verify|v[ée]rifi)", re.I)


# ---------- window / focus ----------

async def activate(page) -> x11.Window:
    """Bring the tab's browser window to the front with OS focus."""
    await page.bring_to_front()
    win = x11.main_window(cdp.browser_pid(), await page.title())
    x11.activate(win)
    await page.wait_for_timeout(400)
    return win


def is_active() -> bool:
    return x11.active_pid() == cdp.browser_pid()


async def real_click(page, locator) -> None:
    """Real click on a field. Clicks inert page content first: Chrome only reopens its
    autofill UI when an unfocused field is clicked."""
    await cdp.blur_all(page)
    b = await cdp.box(locator)
    for point in await cdp.inert_points_near(page, b):   # until no page field has focus
        x11.click(*await cdp.to_screen(page, *point))
        await page.wait_for_timeout(300)
        if not await cdp.editable_focused(page):
            break
    b = await cdp.box(locator)
    x11.click(*await cdp.to_screen(page, b["x"] + min(b["width"] / 2, 80), b["y"] + b["height"] / 2))


# ---------- autofill dropdown ----------

def dropdown() -> x11.Window | None:
    """Chrome's autofill dropdown: a small untitled popup window."""
    pops = [w for w in x11.windows(cdp.browser_pid())
            if not w.title and 150 <= w.width <= 600 and 60 <= w.height <= 700]
    return pops[-1] if pops else None


async def open_dropdown(page, locator) -> x11.Window:
    """Activate Chrome, real-click the field, return the dropdown window."""
    if x11.screen_locked():
        raise BrokerError("desktop is locked; real input cannot reach Chrome")
    await activate(page)
    await real_click(page, locator)
    await page.wait_for_timeout(1500)
    pop = dropdown()
    if not pop:
        raise BrokerError("autofill dropdown did not appear")
    return pop


def dropdown_lines(pop: x11.Window) -> list[ocr.Line]:
    return ocr.lines(x11.screenshot(pop))


def highlight(index: int) -> None:
    """Highlight entry `index` (0-based). A preview only; nothing is committed."""
    for _ in range(index + 1):
        x11.key("Down")


def accept() -> None:
    """Commit the highlighted entry. Callers must check dropdown() first: with no dropdown,
    Enter would hit the page (and could submit a form)."""
    x11.key("Return")


def dismiss() -> None:
    x11.key("Escape")


# ---------- card unmask (CVC) prompt ----------

@dataclass(frozen=True)
class Before:
    windows: frozenset
    words: int


def snapshot() -> Before:
    """State before Enter, to recognise the unmask prompt afterwards."""
    pid = cdp.browser_pid()
    main = x11.main_window(pid)
    return Before(frozenset(w.key for w in x11.windows(pid) if w.id != main.id),
                  ocr.count(x11.screenshot(main), UNMASK_WORDS))


def unmask_prompt_shown(before: Before) -> bool:
    """A new/changed browser window, or prompt words that were not on screen before.
    Screenshots are taken before anything secret is typed."""
    pid = cdp.browser_pid()
    main = x11.main_window(pid)
    if any(w.key not in before.windows and w.width > 100 and w.height > 80
           for w in x11.windows(pid) if w.id != main.id):
        return True
    return ocr.count(x11.screenshot(main), UNMASK_WORDS) > before.words


async def prompt_has_keyboard(page) -> bool:
    """Keystrokes would go to Chrome's prompt, not the page: Chrome is the active window
    and no field in any frame of the page is focused."""
    return is_active() and not await cdp.editable_focused(page)
