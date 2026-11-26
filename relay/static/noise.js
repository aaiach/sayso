// Noise Protocol Framework (rev 34), the two patterns sayso uses, on WebCrypto only:
//   Noise_KK_25519_AESGCM_SHA256      each approval (both static keys pinned)
//   Noise_XXpsk3_25519_AESGCM_SHA256  pairing (psk = one-time key from the QR code)
// Cross-tested against the Python reference library (tests/test_noise_interop.py).
const subtle = globalThis.crypto.subtle;
const enc = new TextEncoder();

export const PATTERNS = {
  KK: { pre: [["s"], ["s"]], msgs: [["e", "es", "ss"], ["e", "ee", "se"]] },
  XXpsk3: { pre: [[], []], msgs: [["e"], ["e", "ee", "s", "es"], ["s", "se", "psk"]] },
};

export const concat = (...parts) => {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let i = 0;
  for (const p of parts) { out.set(p, i); i += p.length; }
  return out;
};
const sha256 = async (b) => new Uint8Array(await subtle.digest("SHA-256", b));
async function hmac(key, data) {
  const k = await subtle.importKey("raw", key, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await subtle.sign("HMAC", k, data));
}
async function hkdf(ck, ikm, n) {
  const t = await hmac(ck, ikm);
  const o1 = await hmac(t, Uint8Array.of(1));
  const o2 = await hmac(t, concat(o1, Uint8Array.of(2)));
  return n === 2 ? [o1, o2] : [o1, o2, await hmac(t, concat(o2, Uint8Array.of(3)))];
}
function nonce(n) {                       // AESGCM: 4 zero bytes || 64-bit big-endian counter
  const b = new Uint8Array(12);
  new DataView(b.buffer).setBigUint64(4, BigInt(n), false);
  return b;
}
async function aead(op, k, n, ad, data) {
  const key = await subtle.importKey("raw", k, "AES-GCM", false, [op]);
  const alg = { name: "AES-GCM", iv: nonce(n), additionalData: ad, tagLength: 128 };
  return new Uint8Array(await subtle[op](alg, key, data));
}

export async function generateKeyPair(extractable = false) {
  const kp = await subtle.generateKey({ name: "X25519" }, extractable, ["deriveBits"]);
  return { privateKey: kp.privateKey, publicKey: new Uint8Array(await subtle.exportKey("raw", kp.publicKey)) };
}
async function dh(kp, pub) {
  const p = await subtle.importKey("raw", pub, { name: "X25519" }, true, []);
  return new Uint8Array(await subtle.deriveBits({ name: "X25519", public: p }, kp.privateKey, 256));
}

export class Handshake {
  // opts: { pattern: "KK" | "XXpsk3", initiator, s (key pair), rs (remote static), psk }
  constructor(opts) { Object.assign(this, opts, { k: null, n: 0, re: null }); this.p = PATTERNS[opts.pattern]; this.i = 0; }

  async init() {
    const name = enc.encode(`Noise_${this.pattern}_25519_AESGCM_SHA256`);
    this.h = name.length <= 32 ? concat(name, new Uint8Array(32 - name.length)) : await sha256(name);
    this.ck = this.h;
    await this.mixHash(new Uint8Array(0));                       // empty prologue
    const [ipre, rpre] = this.p.pre;
    if (ipre.length) await this.mixHash(this.initiator ? this.s.publicKey : this.rs);
    if (rpre.length) await this.mixHash(this.initiator ? this.rs : this.s.publicKey);
    return this;
  }
  async mixHash(d) { this.h = await sha256(concat(this.h, d)); }
  async mixKey(ikm) { [this.ck, this.k] = await hkdf(this.ck, ikm, 2); this.n = 0; }
  async encryptAndHash(pt) {
    const ct = this.k ? await aead("encrypt", this.k, this.n++, this.h, pt) : pt;
    await this.mixHash(ct);
    return ct;
  }
  async decryptAndHash(ct) {
    const pt = this.k ? await aead("decrypt", this.k, this.n++, this.h, ct) : ct;
    await this.mixHash(ct);
    return pt;
  }
  async token(t, writing, msg) {
    const psk = this.pattern.includes("psk");
    const local = { es: this.initiator ? "e" : "s", se: this.initiator ? "s" : "e" };
    if (t === "e") {
      if (writing) { this.e = await generateKeyPair(); msg.out.push(this.e.publicKey); }
      else { this.re = msg.take(32); }
      const pub = writing ? this.e.publicKey : this.re;
      await this.mixHash(pub);
      if (psk) await this.mixKey(pub);
    } else if (t === "s") {
      if (writing) msg.out.push(await this.encryptAndHash(this.s.publicKey));
      else this.rs = await this.decryptAndHash(msg.take(this.k ? 48 : 32));
    } else if (t === "psk") {
      const [ck, th, tk] = await hkdf(this.ck, this.psk, 3);
      this.ck = ck; await this.mixHash(th); this.k = tk; this.n = 0;
    } else {                                                     // ee, es, se, ss
      const mine = t === "ee" ? "e" : t === "ss" ? "s" : local[t];
      const theirs = t === "ee" ? "re" : t === "ss" ? "rs" : (mine === "e" ? "rs" : "re");
      await this.mixKey(await dh(this[mine], this[theirs]));
    }
  }
  async write(payload = new Uint8Array(0)) {
    const msg = { out: [] };
    for (const t of this.p.msgs[this.i++]) await this.token(t, true, msg);
    msg.out.push(await this.encryptAndHash(payload));
    return concat(...msg.out);
  }
  async read(data) {
    let off = 0;
    const msg = { take: (n) => { const b = data.slice(off, off + n); off += n; return b; } };
    for (const t of this.p.msgs[this.i++]) await this.token(t, false, msg);
    return this.decryptAndHash(data.slice(off));
  }
  get finished() { return this.i === this.p.msgs.length; }
}
