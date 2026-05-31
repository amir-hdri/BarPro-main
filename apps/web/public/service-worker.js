/**
 * 🚀 Professional Service Worker for BarPro Automation (Next.js 14)
 * ---------------------------------------------------------------
 * This service worker is optimized for a robust management dashboard.
 * - API calls (/api/*) are NEVER cached (NetworkOnly) to prevent "Network Error" issues.
 * - Static assets are cached using StaleWhileRevalidate for speed.
 * - Navigation pages use NetworkFirst for reliability.
 */

if (!self.define) {
  let e, s = {};
  const a = (a, n) => (
    a = new URL(a + ".js", n).href,
    s[a] || new Promise(s => {
      if ("document" in self) {
        const e = document.createElement("script");
        e.src = a, e.onload = s, document.head.appendChild(e)
      } else e = a, importScripts(a), s()
    }).then(() => {
      let e = s[a];
      if (!e) throw new Error(`Module ${a} didn’t register its module`);
      return e
    })
  );
  self.define = (n, i) => {
    const c = e || ("document" in self ? document.currentScript.src : "") || location.href;
    if (s[c]) return;
    let t = {};
    const r = e => a(e, c), o = { module: { uri: c }, exports: t, require: r };
    s[c] = Promise.all(n.map(e => o[e] || r(e))).then(e => (i(...e), t))
  }
}

define(["./workbox-f1770938"], function (workbox) {
  "use strict";

  // Take control immediately to avoid stale session issues
  self.skipWaiting();
  workbox.clientsClaim();

  // 1. API CACHING: BYPASS COMPLETELY
  // Critical to prevent "Network Error" in Admin Panel and Waybill Submission.
  // POST, PUT, DELETE should never be handled by SW caching strategies.
  workbox.registerRoute(
    ({ url }) => url.pathname.startsWith('/api/'),
    new workbox.NetworkOnly()
  );

  // 2. STATIC ASSETS: StaleWhileRevalidate
  // Fast loading for JS, CSS, and fonts.
  workbox.registerRoute(
    /\.(?:js|css|woff2?|ttf|otf)$/i,
    new workbox.StaleWhileRevalidate({
      cacheName: 'static-assets',
      plugins: [
        new workbox.expiration.ExpirationPlugin({
          maxEntries: 100,
          maxAgeSeconds: 24 * 60 * 60, // 24 hours
        }),
      ],
    })
  );

  // 3. IMAGES: CacheFirst
  workbox.registerRoute(
    /\.(?:png|jpg|jpeg|svg|gif|webp|ico)$/i,
    new workbox.CacheFirst({
      cacheName: 'image-assets',
      plugins: [
        new workbox.expiration.ExpirationPlugin({
          maxEntries: 64,
          maxAgeSeconds: 30 * 24 * 60 * 60, // 30 days
        }),
      ],
    })
  );

  // 4. NAVIGATION: NetworkFirst
  // Ensures the latest version of the app is served, with offline fallback.
  workbox.registerRoute(
    ({ request }) => request.mode === 'navigate',
    new workbox.NetworkFirst({
      cacheName: 'pages',
      plugins: [
        new workbox.expiration.ExpirationPlugin({
          maxEntries: 32,
        }),
      ],
    })
  );

  // Precache minimal set (updated during build)
  workbox.precacheAndRoute([
    { url: '/manifest.json', revision: 'pwa-v1' },
    { url: '/favicon.ico', revision: 'pwa-v1' }
  ], {
    ignoreURLParametersMatching: [/^utm_/, /^fbclid$/]
  });

  // Cleanup old versions
  workbox.cleanupOutdatedCaches();
});
