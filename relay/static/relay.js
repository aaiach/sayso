// Talk to this relay's mailboxes. Envelope = {v: 1, id, noise: base64url}; the id only routes,
// everything that matters is inside the Noise message.
export const b64u = (u) =>
  btoa(String.fromCharCode(...u)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
export const unb64u = (s) =>
  Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)),
    (c) => c.charCodeAt(0));
export const envelope = (id, noise) => ({ v: 1, id, ...(noise ? { noise: b64u(noise) } : {}) });

export async function put(box, slot, env) {
  const r = await fetch(`/mb/${box}/${slot}`, { method: "PUT", body: JSON.stringify(env) });
  if (!r.ok) throw new Error(`relay refused the message (${r.status})`);
  return (await r.json()).seq;
}

// The next message newer than `after`, or null after ~25 s without one.
export async function next(box, slot, after, wait = 25) {
  const r = await fetch(`/mb/${box}/${slot}?after=${after}&wait=${wait}`, { cache: "no-store" });
  if (r.status === 204) return null;
  if (!r.ok) throw new Error(`relay error (${r.status})`);
  return { seq: Number(r.headers.get("X-Seq")), env: await r.json() };
}

export async function waitFor(box, slot, after, seconds) {
  const end = Date.now() + seconds * 1000;
  while (Date.now() < end) {
    const r = await next(box, slot, after);
    if (r) return r;
  }
  throw new Error("timed out waiting for your computer");
}
