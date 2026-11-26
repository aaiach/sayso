"""Relay: mailbox put/get, long-poll wake-up, validation, limits, security headers.

  python tests/test_relay.py
"""
import threading
import time

from starlette.testclient import TestClient

from relay.app import app, boxes

c = TestClient(app).__enter__()      # one client = one event loop, shared across threads
BOX = "A" * 22
assert c.get("/healthz").json() == {"ok": True}
assert c.get(f"/mb/{BOX}/req").status_code == 204, "empty -> 204"
assert c.put(f"/mb/{BOX}/req", content=b"cipher1").json()["seq"] >= 1
r = c.get(f"/mb/{BOX}/req")
assert r.status_code == 200 and r.content == b"cipher1"
seq = int(r.headers["x-seq"])
assert c.get(f"/mb/{BOX}/req?after={seq}").status_code == 204, "nothing newer"
assert c.get(f"/mb/{BOX}/req").content == b"cipher1", "reads don't consume"
assert c.get("/mb/short/req").status_code == 404 and c.get(f"/mb/{BOX}/evil").status_code == 404
assert c.put(f"/mb/{BOX}/ans", content=b"x" * (64 * 1024 + 1)).status_code == 413

def late_put():
    time.sleep(0.5)
    c.put(f"/mb/{BOX}/req", content=b"cipher2")
threading.Thread(target=late_put).start()
t0 = time.time()
r = c.get(f"/mb/{BOX}/req?after={seq}&wait=5")
assert r.status_code == 200 and r.content == b"cipher2" and time.time() - t0 < 4, "long-poll wakes up"

h = c.get("/").headers
assert "default-src 'self'" in h["content-security-policy"] and h["x-content-type-options"] == "nosniff"
assert not boxes.waiting, "no leftover waiters"
print("relay checks passed")
c.__exit__(None, None, None)
