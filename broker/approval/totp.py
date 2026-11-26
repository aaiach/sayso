"""RFC 6238 TOTP (the codes authenticator apps show): SHA-1, 6 digits, 30 s. Stdlib only."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

DIGITS, PERIOD = 6, 30


def new_secret() -> str:
    """160-bit secret, base32 without padding (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def counter(at: float | None = None) -> int:
    return int((time.time() if at is None else at) // PERIOD)


def code(secret_b32: str, ctr: int) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    mac = hmac.new(key, struct.pack(">Q", ctr), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    n = struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF
    return str(n % 10 ** DIGITS).zfill(DIGITS)


def match(secret_b32: str, given: str, after: int, window: int = 1) -> int | None:
    """Counter of the matching code within ±window steps, strictly newer than `after` (so a
    code can't be replayed), else None."""
    now = counter()
    for ctr in range(now - window, now + window + 1):
        if ctr > after and hmac.compare_digest(code(secret_b32, ctr), given):
            return ctr
    return None


def uri(secret_b32: str, account: str, issuer: str = "Credential Broker") -> str:
    return (f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret_b32}"
            f"&issuer={quote(issuer)}&algorithm=SHA1&digits={DIGITS}&period={PERIOD}")
