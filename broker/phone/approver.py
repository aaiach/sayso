"""Approval on the paired phone: one Noise KK exchange per request through the relay.

  msg 1 (broker -> phone, mailbox slot "req"): the request R, readable only by the phone
  msg 2 (phone -> broker, slot "ans"): the decision, authenticated by the phone's key and
         bound to this exact R by the handshake hash (it can't be replayed or moved)

One-tap only for now: requests needing a PIN, an authenticator code or a typed secret go
through the desktop approval window instead (see mcp_server).
"""
from __future__ import annotations

import json
import time
import uuid

from ..approval.request import Request
from ..errors import BrokerError
from . import keys, noise, push, relay_client as relay

TTL_S = 120


def request_payload(req: Request, rid: str, expires: int) -> dict:
    return {"v": 2, "id": rid, "site": req.site, "frame": req.frame, "kind": req.kind,
            "item": req.label, "amount": req.amount, "certificate": req.certificate,
            "warnings": list(req.warnings), "approve_with": "validate", "needs_secret": None,
            "expires": expires}


class PhoneApprover:
    def __init__(self, method: str = "validate"):
        if method != "validate":
            raise BrokerError("phone approval is one-tap only for now; use the desktop window "
                              "for PIN / authenticator approvals")
        self.device = keys.device()
        if not self.device:
            raise BrokerError("no phone paired: run `python -m broker.cli setup`")
        self.push_status = ""

    def approve(self, req: Request) -> bool:
        b_priv, _ = keys.broker_key()
        d, rid = self.device, uuid.uuid4().hex
        expires = int(time.time()) + TTL_S
        hs = noise.approval_initiator(b_priv, keys.unb64u(d["p_pub"]))
        m1 = hs.write_message(json.dumps(request_payload(req, rid, expires)).encode())
        after = relay.latest_seq(d["box"], "ans")
        relay.put(d["box"], "req", relay.envelope(rid, m1))
        self.push_status = push.notify(d.get("push"))
        while (got := relay.wait_for(d["box"], "ans", after, expires)) is not None:
            after = got[0]
            env, m2 = relay.open_envelope(got[1])
            if env.get("id") != rid or m2 is None:
                continue                     # an older answer, or noise: keep waiting
            try:
                ans = json.loads(bytes(hs.read_message(m2)))
            except Exception:
                raise BrokerError("the phone's answer failed authentication (tampered?)")
            if ans.get("id") != rid:
                raise BrokerError("the phone answered a different request")
            return ans.get("decision") == "approve"
        raise BrokerError("no answer from the phone within 2 minutes")

    def secret(self, req: Request, what: str, optional: bool = False):
        raise BrokerError("typing secrets on the phone isn't supported yet")
