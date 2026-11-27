"""Per-instance settings. Read from the environment, then from `.env` at the repo root
(gitignored; copy `.env.example`). Nothing here is a secret by design (Kerckhoffs): secrets
live in the state directory, created per install and never committed."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal KEY=VALUE reader; real environment variables win."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv()


def _path(name: str, default: str) -> Path:
    return Path(os.path.expanduser(os.environ.get(name, default)))


# Browser to drive (Chrome DevTools Protocol endpoint, loopback only) and its profile dir.
CDP_URL = os.environ.get("BROKER_CDP", "http://127.0.0.1:9222")
PROFILE = os.path.expanduser(os.environ.get("BROKER_PROFILE", ""))

# Per-instance non-secret state (known sites).
STATE_DIR = _path("BROKER_STATE_DIR", "~/.local/share/credential-broker")
TRUST_STORE = _path("BROKER_TRUST_STORE", str(STATE_DIR / "known_sites.json"))

# Per-instance secrets (the phone-pairing keys): see vault.py.
SECRET_BACKEND = os.environ.get("BROKER_SECRET_BACKEND", "keyring")
KEYRING_SERVICE = os.environ.get("BROKER_KEYRING_SERVICE", "sayso")

# Phone approval: your self-hosted relay, and which approver to use:
#   auto (default): the paired phone when there is one, the desktop window otherwise
#   phone / terminal: always that one
RELAY_URL = os.environ.get("BROKER_RELAY_URL", "")
APPROVER = os.environ.get("BROKER_APPROVER", "auto")
