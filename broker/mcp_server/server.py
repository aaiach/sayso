"""MCP tools for agents: check a target, fill one secret, see where approvals go.

The agent does everything about the page (navigation, multi-step flows, clicks, retries) and
calls sayso_fill once per secret, at the moment it's needed. No argument carries a secret and
no result contains one. Nothing is ever submitted.
"""
from __future__ import annotations

import asyncio

from mcp.server.mcpserver import MCPServer

import time

from .. import config, inspect_target, runner, spec as sp
from ..approval import window
from ..errors import BrokerError, masked

TARGET_DOC = """target says where the secret goes (locations only, never code), one of:
  {"selector": "#password"}                    CSS or Playwright selector, must match exactly 1 visible field
  {"selector": "input[name=cardnumber]", "frame": "js.stripe.com"}   field inside an iframe
  {"focused": true}                            the field the agent just clicked (custom widgets)
  {"boxes": "input.otp-digit"}                 split code boxes, one character each (from=user codes)
  {"chrome_prompt": true}                      Chrome's own "Enter the CVC" prompt you see open (from=user, cvc)
  {} or omitted                                standard field for that secret (autocomplete hints)"""

SECRET_DOC = """secret says which secret, one of:
  {"from": "user", "what": "one-time code" | "password" | "cvc" | "card_number" | "expiry"}
      the user types it when approving; the broker types it into the target
  {"from": "google_password", "username": "user@example.com"}
  {"from": "google_card", "card": "My Visa", "last4": "4242"}
      saved in Chrome: APPROVAL ONLY. On "approved", open Chrome's autofill on that field
      yourself and pick exactly that entry. If Chrome then asks for the CVC, call again with
      {"from": "user", "what": "cvc"} and target {"chrome_prompt": true}."""

mcp = MCPServer("sayso", instructions=(
    "Fill passwords, one-time codes and cards without seeing them. You drive the page; call "
    "sayso_check to verify a target (no approval needed), then sayso_fill once per secret. "
    "The user approves each fill. Nothing is submitted: press Log in / Continue yourself, "
    "and never press Pay without the user's explicit yes in chat."))
_one_at_a_time = asyncio.Lock()


def _spec(site: str, secret: dict, target: dict | None, label: str = ""):
    return sp.parse({"site": site, "secret": secret, "target": target or {}, "label": label})


@mcp.tool(description="Dry run, no approval, no clicks: resolve the target on the open tab and "
          "report the site (host, certificate issuer, first-visit warnings) and the field found "
          "(frame, tag, type, name, id, autocomplete, empty). Use it to get the target right.\n\n"
          f"site: host of the open tab.\n{TARGET_DOC}\n{SECRET_DOC}")
async def sayso_check(site: str, secret: dict, target: dict | None = None) -> dict:
    try:
        return await inspect_target.check(_spec(site, secret, target))
    except BrokerError as e:
        return {"status": "refused", "reason": str(e)}
    except Exception as e:
        return {"status": "error", "reason": masked(e)}


@mcp.tool(description="Fill ONE secret into ONE target on the open tab, after the user approves "
          "(one approval per call, ~2 min to answer). The broker re-checks the site and field, "
          "types real keystrokes, and returns only a status: filled | partial | approved (Chrome-"
          "saved secrets: you pick the entry) | denied | timeout | refused | error, with a reason "
          "you can act on (e.g. retarget and retry). It never submits.\n\n"
          f"site: host of the open tab.\n{TARGET_DOC}\n{SECRET_DOC}\n"
          "label: what the user sees on the approval card (e.g. 'Example login, SMS code').")
async def sayso_fill(site: str, secret: dict, target: dict | None = None, label: str = "") -> dict:
    try:
        s = _spec(site, secret, target, label)
    except BrokerError as e:
        return {"status": "refused", "reason": str(e)}
    async with _one_at_a_time:
        channel = _channel()
        if channel == "desktop window":
            return {**await asyncio.to_thread(window.run, s.to_dict()), "approved_on": channel}
        try:
            approver = runner.Expiring(_approver(channel, time.time() + 170), time.time() + 170)
        except BrokerError as e:
            return {"status": "refused", "reason": str(e)}
        out = await asyncio.to_thread(lambda: asyncio.run(runner.execute(s, approver)))
        extra = {"push": approver.inner.push_status} if channel == "phone" else {}
        return {**out, "approved_on": channel, **extra}


def _channel() -> str:
    """auto: the paired phone (with a relay), else this computer's desktop notifications,
    else the terminal window. BROKER_APPROVER=phone | local | terminal forces one."""
    forced = {"phone": "phone", "local": "this computer", "terminal": "desktop window"}
    if config.APPROVER in forced:
        return forced[config.APPROVER]
    from ..phone import keys
    if config.RELAY_URL and keys.device() is not None:
        return "phone"
    from ..local import notify
    return "this computer" if notify.available() else "desktop window"


def _approver(channel: str, deadline: float):
    if channel == "phone":
        from ..phone.approver import PhoneApprover
        return PhoneApprover()
    from ..local.approver import LocalApprover
    return LocalApprover(deadline)


@mcp.tool(description="Where approvals go: the paired phone, this computer, or the terminal window.")
async def sayso_status() -> dict:
    from ..phone import keys
    dev = keys.device()
    return {"approvals_on": _channel(),
            "phone": f"paired ({dev['name']})" if dev else "not paired",
            "relay": "set" if config.RELAY_URL else "not set", "secrets_in": config.SECRET_BACKEND}


def main() -> None:
    mcp.run("stdio")
