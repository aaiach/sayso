"""Manual check of local mode on a Linux desktop: raises a notification, then a dialog, and
prints what came back (lengths only, never values). Needs someone at the screen to click.

  PYTHONPATH=. python tests/manual_local_mode.py
"""
import time

from broker.approval.request import Request
from broker.errors import BrokerError
from broker.local.approver import LocalApprover

CASES = [
    ("notification: click Approve or Deny", ()),
    ("dialog: type a fake card (4242 4242 4242 4242, 12/34, 123), Approve", (("card_number", None), ("expiry", None), ("cvc", None))),
]

for title, asks in CASES:
    print(f"\n{title}")
    req = Request(kind="password" if not asks else "card", site="app.example.com", frame="app.example.com",
                  label=f"sayso test: {title}", certificate="app.example.com by Example CA",
                  warnings=("first time on this site",), asks=asks)
    a = LocalApprover(time.time() + 60)
    try:
        ok = a.approve(req)
    except BrokerError as e:
        print("  refused:", e)
        continue
    print("  approved" if ok else "  denied")
    for what, _ in asks if ok else ():
        try:
            print(f"  {what}: {len(a.secret(req, what))} characters")
        except BrokerError as e:
            print(f"  {what}: {e}")
