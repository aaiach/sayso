// Runs the phone's Noise code (relay/static/noise.js) against the official Noise test vectors
// in vectors.json. For every handshake message: ciphertext matches byte for byte, the payload
// decrypts, a single flipped bit is refused; then the handshake hash. Finally checks that a
// wrong expected byte is caught, so a pass can't come from a test that checks nothing.
// Usage (from the repo root): node tests/noise_vectors/run.mjs
import { readFileSync } from "node:fs";

const here = new URL(".", import.meta.url);
const { Handshake } = await import(new URL("../../relay/static/noise.js", here));
const { x25519: noble } = await import(new URL("../../relay/static/vendor/noble-x25519.js", here));
const { vectors } = JSON.parse(readFileSync(new URL("vectors.json", here), "utf8"));

const hex = (s) => new Uint8Array(Buffer.from(s || "", "hex"));
const toHex = (u) => Buffer.from(u).toString("hex");
const keyPair = (s) => (s ? { privateKey: hex(s), publicKey: noble.getPublicKey(hex(s)) } : undefined);

// The vectors fix the prologue and the ephemeral keys; the app uses an empty prologue and fresh
// ephemeral keys. This subclass swaps in only those two inputs: all protocol logic is noise.js's.
class Fixed extends Handshake {
  async mixHash(d) {
    if (!this.prologueDone && d.length === 0) { this.prologueDone = true; d = this.prologue; }
    return super.mixHash(d);
  }
  async token(t, writing, msg) {
    if (!(t === "e" && writing)) return super.token(t, writing, msg);
    this.e = this.fixedE;
    msg.out.push(this.e.publicKey);
    await this.mixHash(this.e.publicKey);
    if (this.pattern.includes("psk")) await this.mixKey(this.e.publicKey);
  }
}

function side(v, who) {
  const psks = v[`${who}_psks`] || [];
  return new Fixed({
    pattern: v.protocol_name.split("_")[1], initiator: who === "init",
    s: keyPair(v[`${who}_static`]), rs: v[`${who}_remote_static`] ? hex(v[`${who}_remote_static`]) : undefined,
    psk: psks.length ? hex(psks[0]) : undefined, prologue: hex(v[`${who}_prologue`]),
    fixedE: keyPair(v[`${who}_ephemeral`]),
  }).init();
}

// A copy of the reader's state, so a tampered message can be tried without disturbing the real one.
const copy = (hs) => Object.assign(Object.create(Object.getPrototypeOf(hs)),
  structuredClone({ ...hs, p: undefined }), { p: hs.p });

async function run(v, log) {
  let failed = 0;
  const check = (ok, what) => { log(`  ${ok ? "ok  " : "FAIL"} ${what}`); if (!ok) failed++; };
  const I = await side(v, "init"), R = await side(v, "resp");
  for (let i = 0; i < I.p.msgs.length; i++) {       // handshake messages only: the app sends no others
    const [writer, reader] = i % 2 ? [R, I] : [I, R];
    const m = v.messages[i];
    const ct = await writer.write(hex(m.payload));
    check(toHex(ct) === m.ciphertext, `message ${i + 1}: ciphertext matches (${ct.length} bytes)`);
    const tampered = ct.slice();
    tampered[tampered.length - 1] ^= 1;
    let refused = false;
    try { await copy(reader).read(tampered); } catch { refused = true; }
    check(refused, `message ${i + 1}: one flipped bit is refused`);
    check(toHex(await reader.read(ct)) === m.payload, `message ${i + 1}: payload decrypts correctly`);
  }
  if (v.handshake_hash) check(toHex(I.h) === v.handshake_hash && toHex(R.h) === v.handshake_hash, "handshake hash matches");
  check(I.finished && R.finished, "both sides finished");
  return failed;
}

let failed = 0;
for (const v of vectors) {
  console.log(`${v.protocol_name}  (${v.source.split(" ")[0]})`);
  failed += await run(v, console.log);
}

// Self-check: change one expected byte; the run must notice.
const bad = structuredClone(vectors[0]);
const c = bad.messages[0].ciphertext;
bad.messages[0].ciphertext = (c[0] === "0" ? "1" : "0") + c.slice(1);
const caught = (await run(bad, () => {})) > 0;
console.log(`self-check: a wrong expected byte is ${caught ? "caught" : "NOT caught"}`);

console.log(failed || !caught ? "\nFAILED" : "\nall Noise test vectors passed");
process.exit(failed || !caught ? 1 : 0);
