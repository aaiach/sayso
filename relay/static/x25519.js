// X25519 for Noise. The browser's WebCrypto when it supports X25519 (the private key is then a
// non-extractable CryptoKey); otherwise the audited noble-curves implementation in vendor/
// (some iOS Safari versions lack X25519 in WebCrypto), with the private key kept as bytes in
// the app's own storage.
import { x25519 as noble } from "./vendor/noble-x25519.js";

const subtle = globalThis.crypto.subtle;
let nativeOk = globalThis.SAYSO_FORCE_NOBLE ? false : null;
let problem = "";                              // which step of the built-in test failed, and how

async function probe(extractable) {
  let step = "generateKey";
  try {
    const a = await subtle.generateKey({ name: "X25519" }, extractable, ["deriveBits"]);
    step = "exportKey";
    const pub = new Uint8Array(await subtle.exportKey("raw", a.publicKey));
    step = "importKey";
    const p = await subtle.importKey("raw", pub, { name: "X25519" }, true, []);
    step = "deriveBits";
    await subtle.deriveBits({ name: "X25519", public: p }, a.privateKey, 256);
    return "";
  } catch (e) {
    return `${step}: ${e?.name || "error"}`;
  }
}

export async function native() {
  if (nativeOk === null) {
    problem = await probe(false);
    if (problem) problem += ` (extractable key: ${(await probe(true)) || "works"})`;
    nativeOk = !problem;
  }
  return nativeOk;
}

// Why the built-in X25519 isn't used ("" when it is, or when the fallback was forced).
export const nativeProblem = () => problem;

export async function generateKeyPair(extractable = false) {
  if (await native()) {
    const kp = await subtle.generateKey({ name: "X25519" }, extractable, ["deriveBits"]);
    return { privateKey: kp.privateKey, publicKey: new Uint8Array(await subtle.exportKey("raw", kp.publicKey)) };
  }
  const sk = noble.utils.randomSecretKey();
  return { privateKey: sk, publicKey: noble.getPublicKey(sk) };
}

export async function dh(kp, pub) {
  if (kp.privateKey instanceof Uint8Array) return noble.getSharedSecret(kp.privateKey, pub);
  const p = await subtle.importKey("raw", pub, { name: "X25519" }, true, []);
  return new Uint8Array(await subtle.deriveBits({ name: "X25519", public: p }, kp.privateKey, 256));
}
