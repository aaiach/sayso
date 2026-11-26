"""Pair a phone (broker side), run by the user in a terminal: show a QR code, run the Noise
XXpsk3 handshake through the relay, confirm the phone's key fingerprint, save the device.

QR link: <relay>/#pair=<mailbox>.<psk>.<broker key>.<push key>  (after # never reaches a server;
the push key is public, it's in the link so the phone can subscribe right when the user taps)
"""
from __future__ import annotations

import json
import os
import socket
import re
import time

from .. import config
from ..errors import BrokerError
from . import keys, noise, relay_client as relay

WINDOW_S = 600
BOX_ID = re.compile(r"[A-Za-z0-9_-]{16,64}")


def link(box: str, psk: bytes, broker_pub: bytes, vapid_pub: str) -> str:
    return (f"{config.RELAY_URL.rstrip('/')}/#pair={box}.{keys.b64u(psk)}.{keys.b64u(broker_pub)}"
            f".{vapid_pub}")


def _show(url: str) -> None:
    try:
        import qrcode
        qr = qrcode.QRCode(border=2)
        qr.add_data(url)
        qr.print_ascii(invert=True)
    except ImportError:
        pass
    print(f"\nScan with your phone's camera, or open this link on the phone:\n  {url}\n"
          "Waiting for the phone (10 min)...")


def _next(box: str, slot: str, after: int, deadline: float) -> tuple[int, dict, bytes | None]:
    got = relay.wait_for(box, slot, after, deadline)
    if got is None:
        raise BrokerError("pairing timed out")
    env, msg = relay.open_envelope(got[1])
    return got[0], env, msg


def pair(confirm=input) -> dict:
    b_priv, b_pub = keys.broker_key()
    _, vapid_pub = keys.vapid()
    box, psk = keys.b64u(os.urandom(16)), os.urandom(32)
    deadline = time.time() + WINDOW_S
    _show(link(box, psk, b_pub, vapid_pub))
    hs = noise.pairing_responder(b_priv, psk)
    seq, _, m1 = _next(box, "a", 0, deadline)
    hs.read_message(m1)
    relay.put(box, "b", relay.envelope("pair", hs.write_message(
        json.dumps({"broker": socket.gethostname()}).encode())))
    _, _, m3 = _next(box, "a", seq, deadline)
    try:
        payload, p_pub = noise.read_final(hs, m3)
    except Exception:
        raise BrokerError("pairing failed: wrong QR code, or someone tampered with the messages")
    info = json.loads(payload)
    if not BOX_ID.fullmatch(str(info.get("box", ""))):
        raise BrokerError("pairing failed: the phone sent an invalid mailbox id")
    fp = keys.fingerprint(p_pub)
    ok = confirm(f"\nPair '{info.get('device', 'phone')}' (key {fp}, also shown on the phone)? [y/N] ")
    if ok.strip().lower() != "y":
        relay.put(box, "b", relay.envelope("pair-refused"))
        return {"status": "refused"}
    keys.save_device({"name": info.get("device", "phone"), "p_pub": keys.b64u(p_pub), "box": info["box"],
                      "push": info.get("push"), "fingerprint": fp, "paired_at": int(time.time())})
    relay.put(box, "b", relay.envelope("pair-ok"))
    return {"status": "paired", "device": info.get("device"), "fingerprint": fp,
            "push": "yes" if info.get("push") else "no (the app must be open to see requests)"}
