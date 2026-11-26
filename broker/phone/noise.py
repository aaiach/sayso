"""Noise handshakes for the phone channel, using the reference `noiseprotocol` library:
XXpsk3 for pairing (psk from the QR code), KK for each approval (both static keys pinned).
Interop with the phone's WebCrypto implementation: tests/test_noise_interop.py."""
from __future__ import annotations

from noise.connection import Keypair, NoiseConnection

PAIRING = b"Noise_XXpsk3_25519_AESGCM_SHA256"
APPROVAL = b"Noise_KK_25519_AESGCM_SHA256"


def _conn(name: bytes, initiator: bool, static_priv: bytes) -> NoiseConnection:
    c = NoiseConnection.from_name(name)
    c.set_as_initiator() if initiator else c.set_as_responder()
    c.set_keypair_from_private_bytes(Keypair.STATIC, static_priv)
    return c


def pairing_responder(broker_priv: bytes, psk: bytes) -> NoiseConnection:
    c = _conn(PAIRING, False, broker_priv)
    c.set_psks(psk)
    c.start_handshake()
    return c


def approval_initiator(broker_priv: bytes, phone_pub: bytes) -> NoiseConnection:
    c = _conn(APPROVAL, True, broker_priv)
    c.set_keypair_from_public_bytes(Keypair.REMOTE_STATIC, phone_pub)
    c.start_handshake()
    return c


def read_final(c: NoiseConnection, msg: bytes) -> tuple[bytes, bytes]:
    """Read the last handshake message: (payload, remote static public key). The library drops
    its handshake state when the handshake ends, so the key is taken from a held reference."""
    hs = c.noise_protocol.handshake_state
    payload = bytes(c.read_message(msg))
    return payload, bytes(hs.rs.public_bytes)
