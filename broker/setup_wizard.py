"""`python -m broker.cli setup`: first-run setup, safe to run again. Checks the secret store,
optionally sets a PIN and an authenticator, and pairs a phone with your relay. Run it directly
in a terminal: it shows one-time secrets (the pairing QR code, the authenticator key)."""
from __future__ import annotations

import sys

from . import config
from .approval import setup
from .errors import BrokerError
from .vault import open_vault


def _yes(q: str) -> bool:
    return input(q).strip().lower() == "y"


def _check_store() -> str:
    v = open_vault()
    v.set("setup-probe", "ok")
    ok = v.get("setup-probe") == "ok"
    v.delete("setup-probe")
    if not ok:
        raise BrokerError("the secret store didn't keep a test value")
    return config.SECRET_BACKEND


def run() -> dict:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise BrokerError("setup needs an interactive terminal")
    out = {"secret_store": _check_store()}
    print(f"sayso setup\n\n1. Secret store: {out['secret_store']}, ok.")
    st = setup.status()
    print("\nApprovals default to one tap. PIN and authenticator code are optional extras.")
    if _yes(f"2. PIN ({st['pin']}). Set or change it? [y/N] "):
        out["pin"] = setup.setup_pin()["status"]
    if _yes(f"3. Authenticator ({st['otp']}). Set it up? [y/N] "):
        out["otp"] = setup.setup_otp()["status"]
    if not config.RELAY_URL:
        print("4. Phone approval: deploy your relay, put its URL in .env as BROKER_RELAY_URL, "
              "then run setup again.")
        return out
    from .phone import keys, pair
    dev = keys.device()
    q = f"replace the paired phone ({dev['name']}, key {dev['fingerprint']})" if dev else "pair a phone"
    if _yes(f"4. Phone approval via {config.RELAY_URL}: {q}? [y/N] "):
        out["phone"] = pair.pair()
    return out
