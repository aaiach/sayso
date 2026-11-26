// Pairing, phone side: Noise XXpsk3 with the one-time key from the QR link, through the relay.
// Link: <relay>/#pair=<mailbox>.<psk>.<broker key>.<push key>
import { Handshake, generateKeyPair } from "./noise.js";
import * as relay from "./relay.js";
import * as store from "./store.js";

const te = new TextEncoder(), td = new TextDecoder();
const same = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

export function parse(link) {
  const m = /#pair=([\w-]+)\.([\w-]+)\.([\w-]+)\.([\w-]+)/.exec(link || "");
  return m && { box: m[1], psk: relay.unb64u(m[2]), b: relay.unb64u(m[3]), vapid: m[4] };
}

export async function fingerprint(pub) {
  const h = new Uint8Array(await crypto.subtle.digest("SHA-256", pub));
  const x = [...h.slice(0, 4)].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `${x.slice(0, 4)} ${x.slice(4)}`;
}

function deviceName() {
  const ua = navigator.userAgent;
  return /iPhone/.test(ua) ? "iPhone" : /iPad/.test(ua) ? "iPad" : /Android/.test(ua) ? "Android phone" : "browser";
}

// Must start right from the user's tap (iOS requires it for permission and subscription).
export async function subscribe(vapid) {
  try {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) return null;
    if ((await Notification.requestPermission()) !== "granted") return null;
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: relay.unb64u(vapid) });
    return sub.toJSON();
  } catch {
    return null;                       // still works while the app is open
  }
}

export async function pair(p, push, status) {
  const P = await generateKeyPair(false);
  const hs = await new Handshake({ pattern: "XXpsk3", initiator: true, s: P, psk: p.psk }).init();
  await relay.put(p.box, "a", relay.envelope("pair", await hs.write()));
  status("Contacting your computer…");
  const m2 = await relay.waitFor(p.box, "b", 0, 120);
  const info = JSON.parse(td.decode(await hs.read(relay.unb64u(m2.env.noise))));
  if (!same(hs.rs, p.b)) throw new Error("this isn't the computer from the QR code");
  const box = relay.b64u(crypto.getRandomValues(new Uint8Array(16)));
  const payload = { device: deviceName(), box, push };
  await relay.put(p.box, "a", relay.envelope("pair", await hs.write(te.encode(JSON.stringify(payload)))));
  const fp = await fingerprint(P.publicKey);
  status(`On your computer, check that the key is ${fp}, then type y.`);
  const done = await relay.waitFor(p.box, "b", m2.seq, 600);
  if (done.env.id !== "pair-ok") throw new Error("pairing was refused on the computer");
  await store.set("pairing", { P, b: p.b, box, broker: info.broker, fingerprint: fp, push: !!push });
  return store.get("pairing");
}
