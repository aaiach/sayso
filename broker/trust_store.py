"""Remembered site fingerprints (trust on first use). Not a gate: it produces warnings that
the approver shows the user ("first time on this site", "new certificate", "different
issuer"). Certificates rotate routinely (often every 60–90 days), so a new fingerprint from
the same issuer is a notice; a different issuer deserves a closer look.

Stored at config.TRUST_STORE (no secrets).
"""
from __future__ import annotations

import json
import os
import time

from . import config
from .browser.identity import Identity

PATH = str(config.TRUST_STORE)


def _load() -> dict:
    try:
        with open(PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def warnings(ident: Identity) -> tuple[str, ...]:
    known = _load().get(ident.host)
    if not known:
        return ("first time on this site",)
    out = []
    if ident.sha256 not in known.get("fingerprints", []):
        out.append("new certificate since last approval")
    if ident.issuer not in known.get("issuers", []):
        out.append(f"different certificate issuer ({ident.issuer}; before: {', '.join(known.get('issuers', []))})")
    return tuple(out)


def remember(ident: Identity) -> None:
    """Record a fingerprint the user approved."""
    data = _load()
    e = data.setdefault(ident.host, {"first_seen": time.strftime("%Y-%m-%d"), "fingerprints": [], "issuers": []})
    if ident.sha256 not in e["fingerprints"]:
        e["fingerprints"].append(ident.sha256)
    if ident.issuer not in e["issuers"]:
        e["issuers"].append(ident.issuer)
    e["last_approved"] = time.strftime("%Y-%m-%d")
    os.makedirs(os.path.dirname(PATH), mode=0o700, exist_ok=True)
    tmp = PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, PATH)
