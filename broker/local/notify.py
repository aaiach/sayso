"""A desktop notification with Approve / Deny, over the freedesktop Notifications D-Bus API
(GNOME, KDE, most Linux desktops). Talks D-Bus directly (jeepney) instead of `notify-send`,
whose output can't be read reliably from a pipe. Linux only."""
from __future__ import annotations

import html
import os
import time

from ..errors import BrokerError

PATH, NAME = "/org/freedesktop/Notifications", "org.freedesktop.Notifications"
CRITICAL = 2              # urgency: stays on screen until answered (GNOME)


def available() -> bool:
    """A desktop session whose notification service supports buttons."""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return False
    try:
        from jeepney import DBusAddress, new_method_call
        from jeepney.io.blocking import open_dbus_connection
        with open_dbus_connection(bus="SESSION") as conn:
            reply = conn.send_and_get_reply(new_method_call(
                DBusAddress(PATH, bus_name=NAME, interface=NAME), "GetCapabilities"), timeout=2)
        return "actions" in reply.body[0]
    except Exception:
        return False


def ask(title: str, body: str, deadline: float) -> str:
    """Shows the notification and returns "approve", "deny" (Deny, dismissed) or "timeout"."""
    from jeepney import DBusAddress, MatchRule, message_bus, new_method_call
    from jeepney.io.blocking import open_dbus_connection

    addr = DBusAddress(PATH, bus_name=NAME, interface=NAME)
    rule = MatchRule(type="signal", interface=NAME, path=PATH)
    with open_dbus_connection(bus="SESSION") as conn:
        conn.send_and_get_reply(message_bus.AddMatch(rule))
        with conn.filter(rule) as signals:
            reply = conn.send_and_get_reply(new_method_call(addr, "Notify", "susssasa{sv}i", (
                "sayso", 0, "dialog-password", title, html.escape(body),
                ["approve", "Approve", "deny", "Deny"], {"urgency": ("y", CRITICAL)}, 0)))
            nid = reply.body[0]
            try:
                return _answer(conn, signals, nid, deadline)
            finally:
                conn.send_and_get_reply(new_method_call(addr, "CloseNotification", "u", (nid,)))


def _answer(conn, signals, nid: int, deadline: float) -> str:
    while (left := deadline - time.time()) > 0:
        try:
            msg = conn.recv_until_filtered(signals, timeout=left)
        except TimeoutError:
            break
        member = msg.header.fields.get(3)         # 3 = MEMBER: the signal's name
        if not msg.body or msg.body[0] != nid:
            continue                               # another app's notification
        if member == "ActionInvoked":
            return "approve" if msg.body[1] == "approve" else "deny"
        if member == "NotificationClosed":
            return "deny"
    return "timeout"


def require() -> None:
    if not available():
        raise BrokerError("no desktop notifications here (needs a Linux desktop session)")
