"""Where a secret may be written — general rules, no per-site allowlist.

- The page must be HTTPS and Chrome must judge it secure (checked in browser/identity.py).
- password / otp: only into the site's own frame or a frame on the same registrable domain
  (login.example.com on www.example.com). Never a foreign frame.
- card / cvc: only into the site's own frame, or a frame from a known payment provider.

The user's approval (which shows the real origin and certificate) is the per-site decision.
"""
from __future__ import annotations

from .errors import BrokerError

# Payment-provider frame hosts. A frame matches if its host equals an entry or ends with
# "." + entry. Extend deliberately: these are the only foreign frames that may receive cards.
PAYMENT_PROVIDERS: tuple[str, ...] = (
    "js.stripe.com",                      # Stripe Elements / Checkout
    "adyen.com",                          # Adyen (checkoutshopper-*.adyen.com)
    "braintreegateway.com",               # Braintree hosted fields
    "checkout.com",                       # Checkout.com Frames
    "squareup.com", "squareupsandbox.com",  # Square
    "paypal.com",                         # PayPal / Braintree card fields
    "recurly.com",                        # Recurly.js
    "chargebee.com",                      # Chargebee
    "worldpay.com", "access.worldpay.com",  # Worldpay
    "mollie.com",                         # Mollie Components
    "pay-iberia-pci.indra-netplus.com",   # Indra card frames (used by some airlines)
)

KINDS = ("password", "otp", "card", "cvc")


def _matches(hostname: str, entry: str) -> bool:
    return hostname == entry or hostname.endswith("." + entry)


def registrable(hostname: str) -> str:
    """Naive registrable domain (last two labels; three for e.g. co.uk / com.au)."""
    parts = hostname.split(".")
    if len(parts) >= 3 and len(parts[-2]) <= 3 and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def frame_allowed(site: str, frame_url: str, kind: str) -> bool:
    if kind not in KINDS:
        return False
    if not frame_url.startswith("https://"):
        return False
    fh = frame_url.split("/")[2]
    if fh == site:
        return True
    if kind in ("password", "otp"):
        return registrable(fh) == registrable(site)
    return any(_matches(fh, p) for p in PAYMENT_PROVIDERS)


def check(site: str, frame_url: str, kind: str) -> None:
    if not frame_allowed(site, frame_url, kind):
        fh = frame_url.split("/")[2] if "://" in frame_url else frame_url
        raise BrokerError(f"{kind} may not be written into frame {fh} on {site}")
