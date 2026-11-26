"""Who the page really is, as Chrome sees it: security state and the TLS certificate
(subject, issuer, expiry, SHA-256 fingerprint of the leaf). Read over CDP's Security domain,
i.e. the same data as Chrome's padlock — not from the page and not from the agent.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
from dataclasses import asdict, dataclass

from ..errors import BrokerError
from . import cdp


@dataclass(frozen=True)
class Identity:
    host: str
    security_state: str      # Chrome's verdict: "secure", "neutral", "insecure", ...
    subject: str
    issuer: str
    valid_to: int            # unix seconds
    sha256: str              # leaf certificate fingerprint

    def as_dict(self) -> dict:
        return asdict(self)


def _name_matches(name: str, host: str) -> bool:
    """RFC 6125: exact, or a wildcard covering exactly one left-most label."""
    name, host = name.lower(), host.lower()
    if name == host:
        return True
    return name.startswith("*.") and host.endswith(name[1:]) and host.count(".") == name.count(".")


def cert_names(der: bytes) -> list[str]:
    """DNS names the leaf certificate is valid for (its subjectAltName list)."""
    from cryptography import x509
    try:
        ext = x509.load_der_x509_certificate(der).extensions.get_extension_for_class(
            x509.SubjectAlternativeName)
    except x509.ExtensionNotFound:
        return []
    return ext.value.get_values_for_type(x509.DNSName)


async def read(page) -> Identity:
    """Identity of the page's top-level site. Raises unless HTTPS and Chrome says secure."""
    host = cdp.host(page.url)
    if not page.url.startswith("https://"):
        raise BrokerError(f"{host} is not HTTPS")
    s = await page.context.new_cdp_session(page)
    try:
        got = asyncio.get_running_loop().create_future()
        s.on("Security.visibleSecurityStateChanged", lambda e: got.done() or got.set_result(e))
        await s.send("Security.enable")
        e = await asyncio.wait_for(got, 5)
    except asyncio.TimeoutError:
        raise BrokerError(f"could not read the certificate of {host}") from None
    finally:
        await s.detach()
    v = e["visibleSecurityState"]
    c = v.get("certificateSecurityState") or {}
    chain = c.get("certificate") or []
    if v.get("securityState") != "secure" or not chain:
        raise BrokerError(f"Chrome does not consider {host} secure ({v.get('securityState')})")
    if c.get("certificateNetworkError") or c.get("certificateHasWeakSignature"):
        raise BrokerError(f"certificate problem on {host}")
    leaf = base64.b64decode(chain[0])
    ident = Identity(host, v["securityState"], c.get("subjectName", ""), c.get("issuer", ""),
                     int(c.get("validTo", 0)), hashlib.sha256(leaf).hexdigest())
    # Chrome already matched the name; checked again here from the certificate itself.
    if not any(_name_matches(n, host) for n in cert_names(leaf)):
        raise BrokerError(f"certificate {ident.subject} does not cover {host}")
    return ident


async def verify_unchanged(page, expected: Identity) -> None:
    """Right before a secret is written: same site, same certificate as approved."""
    now = await read(page)
    if (now.host, now.sha256) != (expected.host, expected.sha256):
        raise BrokerError("site or certificate changed since approval")
