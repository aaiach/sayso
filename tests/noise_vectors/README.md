# Noise test vectors

Checks that the phone app's Noise code (`relay/static/noise.js`) computes exactly what the
Noise specification says, using the official test vectors.

```bash
node tests/noise_vectors/run.mjs        # from the repo root; Node 20+, no dependencies
```

## Why this test exists

sayso uses two Noise protocols ([`PROTOCOL.html`](../../PROTOCOL.html)):

| Protocol | Used for |
|---|---|
| `Noise_XXpsk3_25519_AESGCM_SHA256` | pairing a phone (the psk is the one-time key from the QR code) |
| `Noise_KK_25519_AESGCM_SHA256` | each approval (both sides already know each other's key) |

The broker uses the Python reference library `noiseprotocol`. The phone runs in a browser, and
we found no maintained JavaScript library for these exact protocols that runs on the browser's
built-in crypto. So the phone side is our own short implementation of the Noise handshake
(rev 34), built only on standard primitives: WebCrypto's AES-GCM, SHA-256 and HMAC, and X25519
from WebCrypto or the audited noble-curves library where the browser lacks it (e.g. Safari on iOS 18.2).

Our own handshake code needs outside proof that it's right. Two tests give it:

- `tests/test_noise_interop.py`: the phone code and the Python library complete pairing and
  approvals with each other, and refuse a wrong QR key, an unknown phone and a tampered message.
- **This test**: the phone code produces the same bytes as two independent implementations,
  for fixed inputs published as test vectors.

## What it checks

For each vector, both sides of the handshake run through `noise.js` with the vector's keys,
prologue and payloads. For every handshake message:

1. the ciphertext matches the vector byte for byte (proves every key derivation, hash, nonce
   and the psk position);
2. the other side decrypts the payload;
3. the same message with one bit flipped is refused.

Then the final handshake hash must match. A self-check at the end changes one expected byte and
makes sure the run notices.

The vectors fix the prologue and the ephemeral keys, which the app normally picks itself (empty
prologue, fresh random keys). `run.mjs` swaps in only those two inputs through a small subclass;
everything else is the app's code unchanged.

## What it doesn't prove

Passing is strong evidence, not a formal proof:

- only these inputs are tested; other malformed messages are covered only partly (here and in
  the interop test);
- nothing about timing side channels or the quality of random keys;
- nothing about the app code around Noise (request ids, expiry, key storage);
- the fixed keys go through noble-curves, as on phones without built-in X25519; the built-in
  path is covered by the interop test;
- it runs in Node, so AES-GCM and SHA-256 come from Node, not from Safari.

The Noise patterns themselves have been analysed formally by others (e.g. Noise Explorer);
we use them unchanged.

## Where the vectors come from

`vectors.json` holds three vectors, copied unchanged apart from an added `source` field:

| Vector | Source | Licence |
|---|---|---|
| KK, XXpsk3 | [cacophony](https://github.com/haskell-cryptography/cacophony), the Haskell implementation, via [snow's copy](https://github.com/mcginty/snow/blob/main/tests/vectors/cacophony.txt) | Unlicense |
| KK | [snow](https://github.com/mcginty/snow/blob/main/tests/vectors/snow.txt), the Rust implementation | Apache-2.0 |

Format: the [Noise test vector format](https://github.com/noiseprotocol/noise_wiki/wiki/Test-vectors).
Only the handshake messages are checked: sayso sends its payloads inside the handshake and
never uses Noise transport messages.
