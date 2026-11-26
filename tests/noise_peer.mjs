// Test helper: plays the phone side with relay/static/noise.js, driven over stdin/stdout
// (one JSON object per line, bytes as base64) by tests/test_noise_interop.py.
import { createInterface } from "node:readline";
import { Handshake, generateKeyPair } from "../relay/static/noise.js";

const b64 = (u) => Buffer.from(u).toString("base64");
const unb64 = (s) => new Uint8Array(Buffer.from(s, "base64"));
const say = (o) => process.stdout.write(JSON.stringify(o) + "\n");
const P = await generateKeyPair(false);          // non-extractable, as on the phone
let hs = null;

for await (const line of createInterface({ input: process.stdin })) {
  const m = JSON.parse(line);
  try {
    if (m.cmd === "pub") say({ pub: b64(P.publicKey) });
    else if (m.cmd === "xx_start") {
      hs = await new Handshake({ pattern: "XXpsk3", initiator: true, s: P, psk: unb64(m.psk) }).init();
      say({ msg: b64(await hs.write()) });
    } else if (m.cmd === "xx_read2") {
      await hs.read(unb64(m.msg));
      say({ rs: b64(hs.rs), msg: b64(await hs.write(new TextEncoder().encode(m.payload))), done: hs.finished });
    } else if (m.cmd === "kk_read1") {
      hs = await new Handshake({ pattern: "KK", initiator: false, s: P, rs: unb64(m.b_pub) }).init();
      const req = new TextDecoder().decode(await hs.read(unb64(m.msg)));
      say({ payload: req, msg: b64(await hs.write(new TextEncoder().encode(m.answer))), done: hs.finished });
    } else say({ error: "unknown cmd" });
  } catch (e) {
    say({ error: String(e && e.name || e) });
  }
}
