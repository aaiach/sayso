"""One fill request as the agent describes it: which tab, where, which secret.
Validated here, before any window opens. Contains no secret by construction."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .browser.target import Target
from .errors import BrokerError
from .flows.user_secret import WHAT

SOURCES = ("google_password", "google_card", "user")


@dataclass(frozen=True)
class FillSpec:
    site: str                       # host of the tab; must match the page's real host
    secret: dict                    # {"from": ..., + source-specific keys}
    target: dict = field(default_factory=dict)
    label: str = ""

    @property
    def tgt(self) -> Target:
        return Target.from_dict(self.target)

    def to_dict(self) -> dict:
        return asdict(self)


def _require(d: dict, *keys: str) -> None:
    missing = [k for k in keys if not str(d.get(k, "")).strip()]
    if missing:
        raise BrokerError(f"secret.{missing[0]} is required for from={d.get('from')}")


def parse(d: dict) -> FillSpec:
    unknown = set(d) - {"site", "secret", "target", "label"}
    if unknown:
        raise BrokerError(f"unknown keys: {', '.join(sorted(unknown))}")
    s = FillSpec(str(d.get("site", "")).strip(), dict(d.get("secret") or {}),
                 dict(d.get("target") or {}), str(d.get("label", "")))
    if not s.site or "/" in s.site:
        raise BrokerError("site must be a host name, e.g. app.example.com")
    src = s.secret.get("from")
    if src not in SOURCES:
        raise BrokerError(f"secret.from must be one of {', '.join(SOURCES)}")
    if src == "google_password":
        _require(s.secret, "username")
    elif src == "google_card":
        _require(s.secret, "card", "last4")
        if not str(s.secret["last4"]).isdigit() or len(str(s.secret["last4"])) != 4:
            raise BrokerError("secret.last4 must be 4 digits")
    elif s.secret.get("what") not in WHAT:
        raise BrokerError(f"secret.what must be one of {', '.join(WHAT)}")
    if (s.tgt.boxes or s.tgt.chrome_prompt) and src != "user":
        raise BrokerError("target.boxes / chrome_prompt only work with secrets you type (from=user)")
    return s


def label(s: FillSpec) -> str:
    """What the user sees on the approval card."""
    if s.label:
        return s.label
    return s.secret.get("what", "")
