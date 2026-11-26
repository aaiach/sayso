"""Chrome's window and focus, from outside the page: bring the window forward, real clicks,
close the autofill popup, and tell whether keystrokes would reach Chrome's own prompt.
No screen reading: the agent operates Chrome's popups itself; this only gives the broker
the facts it needs before typing.

Chrome ignores CDP-synthesised input for its autofill UI after earlier attempts, so clicks
are real X11 input via desktop.x11.
"""
from __future__ import annotations

from ..desktop import x11
from . import cdp, focus


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
    await focus.blur_all(page)
    b = await cdp.box(locator)
    for point in await focus.inert_points_near(page, b):   # until no page field has focus
        x11.click(*await cdp.to_screen(page, *point))
        await page.wait_for_timeout(300)
        if not await focus.editable_focused(page):
            break
    b = await cdp.box(locator)
    x11.click(*await cdp.to_screen(page, b["x"] + min(b["width"] / 2, 80), b["y"] + b["height"] / 2))


def dropdown() -> x11.Window | None:
    """Chrome's autofill popup, if open: a small untitled window (found by size, not read)."""
    pops = [w for w in x11.windows(cdp.browser_pid())
            if not w.title and 150 <= w.width <= 600 and 60 <= w.height <= 700]
    return pops[-1] if pops else None


def dismiss() -> None:
    x11.key("Escape")


async def prompt_has_keyboard(page) -> bool:
    """Keystrokes (and Enter) can only go to Chrome's own prompt: Chrome is the active window
    and nothing in the page has focus, no field and no button. If no prompt is actually
    open, typing then falls on the page body, where it does nothing."""
    return is_active() and await focus.nothing_focused(page)
