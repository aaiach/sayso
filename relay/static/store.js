// The phone's own storage (IndexedDB): the pairing, including the phone's static key P as a
// non-extractable CryptoKey (usable for Noise, never readable as bytes, not even by this code).
const DB = "sayso", STORE = "kv";

function open() {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(DB, 1);
    r.onupgradeneeded = () => r.result.createObjectStore(STORE);
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}

async function run(mode, fn) {
  const db = await open();
  return new Promise((resolve, reject) => {
    const req = fn(db.transaction(STORE, mode).objectStore(STORE));
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export const get = (key) => run("readonly", (s) => s.get(key));
export const set = (key, value) => run("readwrite", (s) => s.put(value, key));
export const del = (key) => run("readwrite", (s) => s.delete(key));
