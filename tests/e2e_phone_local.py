"""End to end on one machine: local relay + headless Chrome as the phone + broker pairing and
PhoneApprover, with a throwaway keyring entry. Needs Chrome (BROKER_TEST_CHROME) and port 8787.

  python tests/e2e_phone_local.py
"""
import os
import subprocess
import sys
import threading
import time

os.environ.update(BROKER_KEYRING_SERVICE="sayso-e2e", BROKER_RELAY_URL="http://127.0.0.1:8787")
from playwright.sync_api import sync_playwright  # noqa: E402

from broker.approval.request import Request  # noqa: E402
from broker.phone import keys, pair  # noqa: E402
from broker.phone.approver import PhoneApprover  # noqa: E402
from broker.vault import open_vault  # noqa: E402

CHROME = os.environ.get("BROKER_TEST_CHROME",
                        os.path.expanduser("~/.local/share/chrome-for-testing/current/chrome-linux64/chrome"))
REQ = Request("password", "app.example.com", "app.example.com", "saved password for user@example.com",
              None, "app.example.com by R11, sha256 0123abcd…", ("first time on this site",))


def in_thread(fn):
    box = {}
    t = threading.Thread(target=lambda: box.update(r=fn()), daemon=True)
    t.start()
    return t, box


def answer_on_phone(page, button):
    page.wait_for_selector("#card:not(.hidden)", timeout=20000)
    shown = {k: page.text_content(f"#r-{k}") for k in ("site", "item", "kind", "warn")}
    page.click(f"#{button}")
    return shown


def main():
    relay = subprocess.Popen([sys.executable, "-m", "uvicorn", "relay.app:app", "--port", "8787", "--log-level",
                              "warning"], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    links = []
    pair._show = links.append                                       # capture the QR link
    try:
        time.sleep(1.5)
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROME, headless=True)
            ctx = browser.new_context()
            ctx.grant_permissions(["notifications"], origin="http://127.0.0.1:8787")
            phone = ctx.new_page()
            t, res = in_thread(lambda: pair.pair(confirm=lambda q: print(q.strip()) or "y"))
            while not links:
                time.sleep(0.1)
            phone.goto(links[0])
            phone.click("#pair-btn")
            phone.wait_for_selector("#paired:not(.hidden)", timeout=30000)
            t.join(30)
            print("paired:", res["r"], "| phone shows key", phone.text_content("#p-fp"))
            assert res["r"]["status"] == "paired" and res["r"]["fingerprint"] == phone.text_content("#p-fp")
            for button, expect in (("approve", True), ("deny", False)):
                t, res = in_thread(lambda: PhoneApprover().approve(REQ))
                shown = answer_on_phone(phone, button)
                t.join(30)
                print(f"{button}: approver returned {res['r']} | phone showed {shown}")
                assert res["r"] is expect and shown["site"] == "app.example.com"
            print("phone notice:", phone.text_content("#notice"))
            browser.close()
        print("end-to-end phone checks passed")
    finally:
        relay.terminate()
        for k in ("phone/broker_key", "phone/vapid", "phone/device"):
            open_vault().delete(k)


if __name__ == "__main__":
    main()
