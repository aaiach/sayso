"""Talk to the relay: put an envelope in a mailbox slot, long-poll for a newer one.
Envelope = {"v": 1, "id": <request or pairing id>, "noise": <base64url Noise message>} as JSON;
the id is only for routing (unauthenticated), everything that matters is inside `noise`."""
from __future__ import annotations

import json
import logging
import time

import httpx

from .. import config
from ..errors import BrokerError
from .keys import b64u, unb64u

logging.getLogger("httpx").setLevel(logging.WARNING)      # no per-request lines (mailbox ids) in logs


def _base() -> str:
    if not config.RELAY_URL:
        raise BrokerError("no relay configured: set BROKER_RELAY_URL in .env")
    return config.RELAY_URL.rstrip("/")


def envelope(id_: str, noise: bytes | None = None, **extra) -> bytes:
    return json.dumps({"v": 1, "id": id_, **({"noise": b64u(noise)} if noise is not None else {}),
                       **extra}).encode()


def open_envelope(data: bytes) -> tuple[dict, bytes | None]:
    e = json.loads(data)
    return e, unb64u(e["noise"]) if e.get("noise") else None


def put(box: str, slot: str, data: bytes) -> int:
    r = httpx.put(f"{_base()}/mb/{box}/{slot}", content=data, timeout=15)
    if r.status_code != 200:
        raise BrokerError(f"relay refused the message ({r.status_code})")
    return r.json()["seq"]


def latest_seq(box: str, slot: str) -> int:
    r = httpx.get(f"{_base()}/mb/{box}/{slot}", timeout=15)
    return int(r.headers.get("x-seq", 0)) if r.status_code == 200 else 0


def wait_for(box: str, slot: str, after: int, deadline: float) -> tuple[int, bytes] | None:
    """Next message newer than `after`, or None once `deadline` (epoch s) passes."""
    while (left := deadline - time.time()) > 0:
        try:
            r = httpx.get(f"{_base()}/mb/{box}/{slot}", params={"after": after, "wait": min(left, 25)},
                          timeout=min(left, 25) + 10)
        except httpx.TransportError:
            time.sleep(1)
            continue
        if r.status_code == 200:
            return int(r.headers["x-seq"]), r.content
    return None
