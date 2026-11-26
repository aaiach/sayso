"""One-time setup of the PIN and authenticator methods, run by the user at a terminal.
Run these directly (not through bin/broker-terminal's logged session): setup-otp shows the
authenticator secret on screen."""
from __future__ import annotations

import getpass
import socket
import sys

from ..errors import BrokerError
from . import methods, store, totp


def _tty() -> None:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise BrokerError("setup needs an interactive terminal")


def setup_pin() -> dict:
    _tty()
    pin = getpass.getpass("New PIN, 4-8 digits (hidden): ")
    if getpass.getpass("Same PIN again (hidden): ") != pin:
        raise BrokerError("PINs differ; nothing saved")
    methods.set_pin(pin)
    return {"status": "pin_set"}


def setup_otp(account: str = "") -> dict:
    _tty()
    account = account or socket.gethostname()
    secret = totp.new_secret()
    uri = totp.uri(secret, account)
    try:
        import qrcode
        qr = qrcode.QRCode(border=2)
        qr.add_data(uri)
        qr.print_ascii(invert=True)
    except ImportError:
        pass
    print("Scan with your authenticator app, or enter this key by hand:\n  "
          + " ".join(secret[i:i + 4] for i in range(0, len(secret), 4)))
    methods.set_otp_secret(secret, getpass.getpass("\nCode the app shows now (hidden): "))
    print("\033[2J\033[H", end="")     # clear the screen so the key doesn't stay visible
    return {"status": "otp_set"}


def status() -> dict:
    out = {}
    for name in ("pin", "otp"):
        s = store.section(name)
        out[name] = ("not set up" if not s else
                     "locked" if s.get("failures", 0) >= methods.MAX_FAILURES else
                     f"ready ({s.get('failures', 0)} recent wrong attempts)")
    out["validate"] = "ready"
    return out
