"""Interop: the phone's Noise (relay/static/noise.js, run in Node) against the Python reference
library (noiseprotocol) the broker uses. Both patterns, plus wrong-key and tamper cases.

  python tests/test_noise_interop.py
"""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from noise.connection import Keypair, NoiseConnection

HERE = Path(__file__).parent
b64, unb64 = (lambda b: base64.b64encode(bytes(b)).decode()), base64.b64decode


def keypair():
    k = X25519PrivateKey.generate()
    return (k.private_bytes(ser.Encoding.Raw, ser.PrivateFormat.Raw, ser.NoEncryption()),
            k.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw))


class Phone:
    def __init__(self):
        self.p = subprocess.Popen(["node", str(HERE / "noise_peer.mjs")], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True, env={**os.environ})

    def __call__(self, **m):
        self.p.stdin.write(json.dumps(m) + "\n")
        self.p.stdin.flush()
        return json.loads(self.p.stdout.readline())


def broker(pattern, b_priv, initiator, psk=None, rs=None):
    c = NoiseConnection.from_name(f"Noise_{pattern}_25519_AESGCM_SHA256".encode())
    c.set_as_initiator() if initiator else c.set_as_responder()
    c.set_keypair_from_private_bytes(Keypair.STATIC, b_priv)
    if rs:
        c.set_keypair_from_public_bytes(Keypair.REMOTE_STATIC, rs)
    if psk:
        c.set_psks(psk)
    c.start_handshake()
    return c


def pairing(phone, b, psk_phone, psk_broker):
    """XXpsk3, phone initiates. Returns (broker's view of phone key, msg3 payload) or raises."""
    br = broker("XXpsk3", b[0], initiator=False, psk=psk_broker)
    m1 = phone(cmd="xx_start", psk=b64(psk_phone))
    br.read_message(unb64(m1["msg"]))
    r = phone(cmd="xx_read2", msg=b64(br.write_message(b"")), payload="device=test")
    if "error" in r:
        raise RuntimeError(r["error"])
    hs = br.noise_protocol.handshake_state      # the library drops it once the handshake ends
    payload = bytes(br.read_message(unb64(r["msg"])))
    assert unb64(r["rs"]) == b[1], "phone learned the broker key"
    return bytes(hs.rs.public_bytes), payload


def approval(phone, b, p_pub, tamper=False):
    """KK, broker initiates with the request; phone answers."""
    br = broker("KK", b[0], initiator=True, rs=p_pub)
    m1 = bytearray(br.write_message(b'{"id":"r1","site":"bank.example.com"}'))
    if tamper:
        m1[-1] ^= 1
    r = phone(cmd="kk_read1", msg=b64(m1), b_pub=b64(b[1]), answer='{"id":"r1","decision":"approve"}')
    if "error" in r:
        raise RuntimeError(r["error"])
    return r["payload"], bytes(br.read_message(unb64(r["msg"]))).decode()


def expect_fail(name, fn):
    try:
        fn()
    except Exception as e:
        return print(f"  {name}: refused ({type(e).__name__ if not str(e) else e})")
    sys.exit(f"FAIL {name}: should have been refused")


def main():
    phone, b, psk = Phone(), keypair(), os.urandom(32)
    info = phone(cmd="pub")
    p_pub = unb64(info["pub"])
    print("phone X25519:", "browser built-in" if info["native"] else "noble-curves fallback")
    seen, payload = pairing(phone, b, psk, psk)
    assert seen == p_pub and payload == b"device=test"
    print("XXpsk3 pairing: ok (keys exchanged, msg3 payload authenticated)")
    req, ans = approval(phone, b, p_pub)
    assert "bank.example.com" in req and '"approve"' in ans
    print("KK approval: ok (request read by phone, answer read by broker)")
    expect_fail("pairing with a wrong QR key", lambda: pairing(Phone(), b, os.urandom(32), psk))
    stranger = Phone()
    expect_fail("approval for a stranger's phone key", lambda: approval(stranger, b, p_pub))
    expect_fail("tampered request", lambda: approval(phone, b, p_pub, tamper=True))
    print("all interop checks passed")


if __name__ == "__main__":
    main()
