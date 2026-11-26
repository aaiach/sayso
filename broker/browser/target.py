"""Where the agent says a secret goes, resolved to exactly one checked field (or N boxes).

The agent passes locations only, never code: a selector (CSS or Playwright syntax), the frame
host when the field is in an iframe, `focused` (the field the agent just clicked), `boxes`
(a selector matching the single-character boxes of a split code), or `chrome_prompt`
(Chrome's own CVC prompt, which the agent has just seen open). Ambiguity is an error the
agent can fix; frame and field-type rules come from policy and the secret kind.
"""
from __future__ import annotations

from dataclasses import dataclass

from .. import policy
from ..errors import BrokerError
from . import cdp, covered, focus

TEXTLIKE = {"text", "tel", "number", "email", "password", ""}
FIELD_TYPES = {"password": {"password"}, "otp": TEXTLIKE - {"email"},
               "card": {"text", "tel", "number", ""}, "cvc": {"text", "tel", "number", "password", ""}}

_FACTS_JS = """e => ({tag: e.tagName, type: (e.getAttribute('type') || '').toLowerCase(),
    name: e.name || '', id: e.id || '', autocomplete: e.autocomplete || '',
    editable: e.isContentEditable, disabled: !!e.disabled})"""


@dataclass(frozen=True)
class Target:
    selector: str | None = None
    frame: str | None = None
    focused: bool = False
    boxes: str | None = None
    chrome_prompt: bool = False

    @classmethod
    def from_dict(cls, d: dict | None) -> "Target":
        d = d or {}
        unknown = set(d) - {"selector", "frame", "focused", "boxes", "chrome_prompt"}
        if unknown:
            raise BrokerError(f"unknown target keys: {', '.join(sorted(unknown))}")
        t = cls(d.get("selector"), d.get("frame"), bool(d.get("focused")), d.get("boxes"),
                bool(d.get("chrome_prompt")))
        if sum([bool(t.selector), t.focused, bool(t.boxes), t.chrome_prompt]) > 1:
            raise BrokerError("give one of selector, focused, boxes or chrome_prompt")
        return t

    @property
    def given(self) -> bool:
        return bool(self.selector or self.focused or self.boxes or self.chrome_prompt)


def _frames(page, t: Target):
    if not t.frame:
        return page.frames
    fs = [f for f in page.frames if cdp.host(f.url) == t.frame or cdp.host(f.url).endswith("." + t.frame)]
    if not fs:
        raise BrokerError(f"no frame on {t.frame}")
    return fs


async def facts(locator) -> dict:
    """What the field is (never its value)."""
    return await locator.evaluate(_FACTS_JS)


async def _check_field(page, frame, locator, kind: str, types: set[str]) -> None:
    policy.check(cdp.host(page.url), frame.url, kind)
    f = await facts(locator)
    if f["disabled"]:
        raise BrokerError("field is disabled")
    if not (f["tag"] == "TEXTAREA" and kind == "otp" or f["editable"]
            or f["tag"] == "INPUT" and f["type"] in types):
        raise BrokerError(f"field is <{f['tag'].lower()} type={f['type'] or 'text'}>, "
                          f"not allowed for {kind} (allowed: {', '.join(sorted(t or 'text' for t in types))})")


async def _visible(frame, selector: str) -> list:
    loc = frame.locator(selector)
    return [loc.nth(i) for i in range(await loc.count()) if await covered.reachable(loc.nth(i))]


async def resolve(page, t: Target, kind: str, default: str, types: set[str] | None = None):
    """(frame, locator): the one field the secret goes into."""
    types = FIELD_TYPES[kind] if types is None else types
    if t.focused:
        hits = [(f, f.locator(":focus")) for f in _frames(page, t)
                if await focus.frame_has_editable_focus(f)]
    elif t.selector:
        hits = [(f, l) for f in _frames(page, t) for l in await _visible(f, t.selector)]
    else:
        frame, loc = await cdp.find_field(page, default, kind)
        hits = [(frame, loc)]
    if len(hits) != 1:
        what = "focused field" if t.focused else repr(t.selector)
        raise BrokerError(f"{what} matched {len(hits)} visible, uncovered fields; need exactly 1")
    frame, loc = hits[0]
    await _check_field(page, frame, loc, kind, types)
    return frame, loc


async def resolve_boxes(page, t: Target, kind: str = "otp"):
    """(frame, [locators]) of split-code boxes, in page order, all in one frame."""
    per_frame = [(f, await _visible(f, t.boxes)) for f in _frames(page, t)]
    per_frame = [(f, bs) for f, bs in per_frame if bs]
    if len(per_frame) != 1:
        raise BrokerError(f"boxes {t.boxes!r} found in {len(per_frame)} frames; need exactly 1")
    frame, boxes = per_frame[0]
    for b in boxes:
        await _check_field(page, frame, b, kind, FIELD_TYPES[kind])
    return frame, boxes
