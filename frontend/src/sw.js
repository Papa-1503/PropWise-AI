import { precacheAndRoute } from "workbox-precaching";
import { clientsClaim } from "workbox-core";

/**
 * Custom service worker source, replacing vite-plugin-pwa's previous
 * fully auto-generated one (generateSW strategy) — Priority 8 needed
 * custom `push`/`notificationclick` event handling, which generateSW's
 * automatic generation doesn't support. Switching to injectManifest
 * means precaching (previously fully automatic) has to be wired up
 * explicitly here instead — precacheAndRoute(self.__WB_MANIFEST) below
 * replicates exactly what generateSW was already doing.
 *
 * Does NOT affect the earlier Cache-Control header fix for index.html
 * staleness — that fix lives in Render's static-site header rules
 * (server-side HTTP response headers), a completely separate layer
 * from the service worker's own caching, so switching service worker
 * strategy has no bearing on it either way.
 */

precacheAndRoute(self.__WB_MANIFEST);
self.skipWaiting();
clientsClaim();

self.addEventListener("push", (event) => {
  let data = { title: "PropWise", body: "You have a new notification.", link: "/" };
  try {
    if (event.data) data = { ...data, ...event.data.json() };
  } catch {
    // Malformed or missing payload — fall back to the generic message
    // above rather than silently showing nothing.
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: { link: data.link },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const link = event.notification.data?.link || "/";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      // Focus an already-open PropWise tab/window if one exists, rather
      // than always opening a new one.
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && "focus" in client) {
          client.navigate(link);
          return client.focus();
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(link);
    })
  );
});
