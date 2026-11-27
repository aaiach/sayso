// sayso phone app: screens and wiring. Pairing in pair.js, approvals in approve.js.
import { listen, pollNow } from "./approve.js";
import { build } from "./ask.js";
import { pair, parse, subscribe } from "./pair.js";
import * as store from "./store.js";
import { native, nativeProblem } from "./x25519.js";

const VERSION = "5";                          // shown on screen, to tell which app build is running
const $ = (id) => document.getElementById(id);
const show = (id, on = true) => $(id).classList.toggle("hidden", !on);
const status = (t) => { $("status").textContent = t; };
const isIOS = /iPhone|iPad/.test(navigator.userAgent);
const iosVersion = (navigator.userAgent.match(/OS (\d+[_\d]*) like Mac/) || [])[1]?.replaceAll("_", ".");
// Shown under the app: why the built-in X25519 failed, and the iOS version (no other device data).
const diag = () => (nativeProblem() ? ` · built-in failed at ${nativeProblem()}` : "") + (iosVersion ? ` · iOS ${iosVersion}` : "");
const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

const ui = {
  notice: (t) => { $("notice").textContent = t; },
  checked: () => { $("p-seen").textContent = `Relay checked at ${new Date().toLocaleTimeString()}`; },
  ask: (R) => new Promise((resolve) => {
    $("r-site").textContent = R.site;
    $("r-item").textContent = R.item;
    $("r-kind").textContent = R.kind;
    $("r-frame").textContent = R.frame === R.site ? "" : `field inside ${R.frame}`;
    $("r-cert").textContent = R.certificate;
    $("r-warn").replaceChildren(...R.warnings.map((w) => Object.assign(document.createElement("li"), { textContent: w })));
    let typed = null;
    const asks = R.asks || [];
    const ready = () => { $("approve").disabled = !!typed && !typed.valid(); };
    typed = asks.length ? build($("r-ask"), asks, ready) : null;
    if (!typed) $("r-ask").replaceChildren();
    ready();
    show("card");
    if (navigator.vibrate) navigator.vibrate(200);
    const finish = (decision) => {
      clearInterval(tick);
      const secrets = decision === "approve" && typed ? typed.values() : null;
      typed?.clear();                                    // nothing typed stays on screen
      show("card", false);
      resolve(decision && { decision, secrets });
    };
    const tick = setInterval(() => {
      const left = Math.round(R.expires - Date.now() / 1000);
      $("r-time").textContent = `${Math.max(left, 0)} s left`;
      if (left <= 0) finish(null);
    }, 500);
    $("approve").onclick = () => { if (!typed || typed.valid()) finish("approve"); };
    $("deny").onclick = () => finish("deny");
  }),
};

function paired(p) {
  show("pair", false);
  show("paired");
  $("p-broker").textContent = p.broker;
  $("p-fp").textContent = p.fingerprint;
  $("p-push").textContent = p.push ? "on" : "off (keep this app open to see requests)";
  status("Waiting for requests…");
  $("p-seen").textContent = "Connecting to the relay…";
  native().then((n) => { $("crypto").textContent = `App v${VERSION} · key exchange: ${n ? "built in" : "noble-curves"}${diag()}`; });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) pollNow(); });
  addEventListener("pageshow", pollNow);
  navigator.serviceWorker?.addEventListener("message", (e) => { if (e.data === "poll") pollNow(); });
  listen(p, ui);
}

async function startPairing(link) {
  $("pair-btn").disabled = true;
  try {
    const push = await subscribe(link.vapid);          // first, while the tap still counts
    const p = await pair(link, push, status);
    history.replaceState(null, "", location.pathname);
    paired(p);
  } catch (e) {
    status(`Pairing failed: ${e.message}`);
    $("pair-btn").disabled = false;
  }
}

function pairingScreen() {
  show("pair");
  native().then((n) => { $("crypto").textContent = `Key exchange: ${n ? "built into this browser" : "noble-curves"}${diag()}`; });
  const link = parse(location.hash);
  if (link && isIOS && !standalone) {
    status("First add sayso to your Home Screen (Share → Add to Home Screen). Then copy the pairing " +
           "link below, open sayso from the Home Screen and tap Paste pairing link.");
    show("copy-btn");
    $("copy-btn").onclick = async () => { await navigator.clipboard.writeText(location.href); ui.notice("Copied."); };
    return;
  }
  if (link) {
    status("Ready to pair with your computer.");
    show("pair-btn");
    $("pair-btn").onclick = () => startPairing(link);
    return;
  }
  status("On your computer, run: python -m broker.cli setup — then scan its QR code.");
  show("paste-btn");
  $("paste-btn").onclick = async () => {
    const l = parse(await navigator.clipboard.readText().catch(() => prompt("Paste the pairing link")));
    if (!l) return ui.notice("That isn't a sayso pairing link.");
    show("paste-btn", false);              // a fresh tap below: iOS asks for notifications only on a tap
    status("Pairing link found.");
    show("pair-btn");
    $("pair-btn").onclick = () => startPairing(l);
  };
}

$("unpair").onclick = async () => {
  if (!confirm("Unpair this phone? You'll need to pair again to approve requests.")) return;
  await store.del("pairing");
  location.reload();
};

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
const p = await store.get("pairing");
p ? paired(p) : pairingScreen();
