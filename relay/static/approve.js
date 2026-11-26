// Approvals, phone side: read each request (Noise KK msg 1), show it, send the decision (msg 2).
// The decision is bound to this exact request by the handshake; a tampered request fails to
// decrypt and is never shown.
import { Handshake } from "./noise.js";
import * as relay from "./relay.js";
import * as store from "./store.js";

const te = new TextEncoder(), td = new TextDecoder();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function handle(pairing, env, ui) {
  const seen = (await store.get("seen")) || [];
  if (!env.noise || seen.includes(env.id)) return;
  const hs = await new Handshake({ pattern: "KK", initiator: false, s: pairing.P, rs: pairing.b }).init();
  let R;
  try {
    R = JSON.parse(td.decode(await hs.read(relay.unb64u(env.noise))));
  } catch {
    return ui.notice("A request failed authentication and was ignored.");
  }
  if (R.id !== env.id) return;
  if (R.expires * 1000 < Date.now()) return ui.notice("A request arrived after it had expired.");
  const decision = await ui.ask(R);                  // "approve" | "deny" | null (expired)
  await store.set("seen", [...seen.slice(-50), R.id]);
  if (!decision) return ui.notice("That request expired.");
  const answer = await hs.write(te.encode(JSON.stringify({ id: R.id, decision })));
  await relay.put(pairing.box, "ans", relay.envelope(R.id, answer));
  ui.notice(decision === "approve" ? `Approved: ${R.item} on ${R.site}` : "Denied.");
}

let wake = null;

// Drop the current wait and ask the relay again at once: called when the app comes back to the
// screen, since iOS may have silently cut the connection while the app was in the background.
export function pollNow() { wake?.abort(); }

// Long-polls the phone's mailbox while the app is open (push only wakes the app up).
export async function listen(pairing, ui) {
  let after = (await store.get("after")) || 0;
  for (;;) {
    wake = new AbortController();
    try {
      const r = await relay.next(pairing.box, "req", after, 25, wake.signal);
      ui.checked();
      if (!r) continue;
      after = r.seq;
      await store.set("after", after);
      await handle(pairing, r.env, ui);
    } catch (e) {
      if (e.name === "AbortError") continue;          // timed out or woken up: ask again now
      ui.notice(`Connection problem, retrying… (${e.message})`);
      await sleep(3000);
    }
  }
}
