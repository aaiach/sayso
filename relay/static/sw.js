// Service worker: shows the "approval waiting" notification (the push carries no details) and
// opens the app when it's tapped. The request itself is fetched and decrypted by the app.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (e) => {
  e.waitUntil(self.registration.showNotification("sayso: approval waiting", {
    body: "Tap to review the request.",
    tag: "sayso-approval",
    renotify: true,
    requireInteraction: true,
  }));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    if (wins.length) return wins[0].focus();
    return self.clients.openWindow("/");
  })());
});
