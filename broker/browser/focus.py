"""Where keyboard focus is, inside the page (any frame): blur, find inert spots to click,
and tell whether a field, or nothing at all, has focus. Read-only except `blur_all`."""
from __future__ import annotations


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


# A document keeps its activeElement even when it doesn't have the keyboard (e.g. while
# Chrome's CVC prompt is open, a payment frame still lists its card field as active), so an
# element only counts if its own document has focus.
_NOTHING_FOCUSED_JS = """() => { const e = document.activeElement;
    return !document.hasFocus() || !e || e === document.body || e === document.documentElement
        || e.tagName === 'IFRAME'; }"""


async def nothing_focused(page) -> bool:
    """No field, button or link has the keyboard in any frame (an Enter would do nothing).
    Unreadable frames count as focused."""
    for f in page.frames:
        try:
            if not await f.evaluate(_NOTHING_FOCUSED_JS):
                return False
        except Exception:
            if not f.is_detached() and f.url.startswith("http"):
                return False
    return True


async def frame_has_editable_focus(frame) -> bool:
    try:
        return await frame.evaluate(_EDITABLE_FOCUSED_JS)
    except Exception:
        return False


async def is_focused(frame, locator) -> bool:
    """True if `locator` is the focused element of a focused frame."""
    return await locator.evaluate("e => document.hasFocus() && document.activeElement === e")
