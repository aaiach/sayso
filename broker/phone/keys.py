"""The broker's phone-channel keys and the paired phone, all kept in the vault (OS keyring):

  phone/broker_key  X25519 static key B (raw private bytes), made at first pairing
  phone/vapid       P-256 key for Web Push (PEM), made at first pairing
  phone/device      the paired phone: its static key P, mailbox, push subscription
"""
from __future__ import annotations

import base64
import hashlib
import json

from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from ..vault import open_vault


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def unb64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def fingerprint(pub: bytes) -> str:
    """Short key fingerprint people compare on two screens: 'ab12 cd34'."""
    h = hashlib.sha256(pub).hexdigest()[:8]
    return f"{h[:4]} {h[4:]}"


def broker_key() -> tuple[bytes, bytes]:
    """(private, public) raw X25519 bytes; created once."""
    v = open_vault()
    raw = v.get("phone/broker_key")
    if raw is None:
        k = X25519PrivateKey.generate()
        raw = b64u(k.private_bytes(ser.Encoding.Raw, ser.PrivateFormat.Raw, ser.NoEncryption()))
        v.set("phone/broker_key", raw)
    k = X25519PrivateKey.from_private_bytes(unb64u(raw))
    return unb64u(raw), k.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)


def vapid() -> tuple[bytes, str]:
    """(private key PEM, public key as the browser's applicationServerKey); created once."""
    v = open_vault()
    pem = v.get("phone/vapid")
    if pem is None:
        k = ec.generate_private_key(ec.SECP256R1())
        pem = k.private_bytes(ser.Encoding.PEM, ser.PrivateFormat.PKCS8, ser.NoEncryption()).decode()
        v.set("phone/vapid", pem)
    k = ser.load_pem_private_key(pem.encode(), None)
    pub = k.public_key().public_bytes(ser.Encoding.X962, ser.PublicFormat.UncompressedPoint)
    return pem.encode(), b64u(pub)


def device() -> dict | None:
    raw = open_vault().get("phone/device")
    return json.loads(raw) if raw else None


def save_device(d: dict) -> None:
    open_vault().set("phone/device", json.dumps(d))


def forget_device() -> None:
    open_vault().delete("phone/device")
