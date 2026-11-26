"""Is a field really on screen, or hidden under something else?

Pages keep decoy fields (e.g. a password input underneath a button, for password managers).
Playwright calls those "visible"; a user could never type into them. A field counts as
reachable only if, at one of a few points across it, the topmost element in its own document
is the field itself (or something inside it). Elements with pointer-events: none, such as
floating labels, don't count as covering.
"""
from __future__ import annotations

_JS = """e => {
  if (e.scrollIntoViewIfNeeded) e.scrollIntoViewIfNeeded(true);   // only if off screen
  else e.scrollIntoView({block: 'center', inline: 'nearest'});
  const r = e.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return false;
  const pts = [[.5, .5], [.2, .5], [.8, .5], [.5, .25], [.5, .75]];
  return pts.some(([fx, fy]) => {
    const top = e.ownerDocument.elementFromPoint(r.left + r.width * fx, r.top + r.height * fy);
    return !!top && (top === e || e.contains(top) || (top.shadowRoot && top.shadowRoot.contains(e)));
  });
}"""


async def reachable(locator) -> bool:
    """True if the user could click this field: visible and not covered by another element."""
    return await locator.is_visible() and await locator.evaluate(_JS)
