"""Wake the phone with a Web Push notification (RFC 8291 encryption, RFC 8292 VAPID), sent by the
broker straight to the phone's push service; the relay is not involved. The notification
says only that an approval is waiting: the request itself travels through the relay, encrypted."""
from __future__ import annotations

import json

from .. import config
from .keys import vapid


def notify(subscription: dict | None) -> str:
    """Best effort: returns 'sent', 'no subscription' or a short error (approval still works if
    the user opens the app)."""
    if not subscription:
        return "no subscription"
    from py_vapid import Vapid02
    from pywebpush import WebPushException, webpush
    pem, _ = vapid()
    try:
        webpush(subscription, json.dumps({"t": "approval"}), vapid_private_key=Vapid02.from_pem(pem),
                vapid_claims={"sub": config.RELAY_URL or "https://localhost"}, ttl=120, timeout=10)
        return "sent"
    except WebPushException as e:
        return f"push failed ({e.response.status_code if e.response is not None else 'network'})"
    except Exception as e:  # never let a push problem block the approval
        return f"push failed ({type(e).__name__})"
