/* Service worker for the blog admin, scoped to /admin/.
 *
 * Its only job is making the editor open with no connection. Drafts themselves
 * live in localStorage and are handled by the page — this just makes sure there
 * is a page to run.
 *
 * Bump VERSION on any change here; activate() drops every other cache, which is
 * also the way out if a bad worker ever ships.
 */
var VERSION = 'blog-admin-v1';

// Best-effort. A 404 on one of these must not fail the install and leave the
// editor with no worker at all.
var SHELL = [
  '/admin/blog',
  '/admin/manifest.json',
  '/admin/favicon.png',
  '/images/app-icon-192.png',
  '/images/app-icon-512.png',
  'https://cdn.jsdelivr.net/npm/geist@1.7.2/dist/fonts/geist-sans/Geist-Regular.woff2',
  'https://cdn.jsdelivr.net/npm/geist@1.7.2/dist/fonts/geist-sans/Geist-Medium.woff2',
  'https://cdn.jsdelivr.net/npm/geist@1.7.2/dist/fonts/geist-sans/Geist-SemiBold.woff2',
  'https://cdn.jsdelivr.net/npm/geist@1.7.2/dist/fonts/geist-mono/GeistMono-Regular.woff2'
];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(VERSION).then(function (cache) {
      return Promise.all(SHELL.map(function (url) {
        return cache.add(new Request(url, { cache: 'reload' })).catch(function () {});
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        return k === VERSION ? null : caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (event) {
  var req = event.request;

  // Writes must never be cached or replayed by the worker. If a save fails the
  // page needs to hear about it so it can keep the text on the device — a
  // worker that quietly absorbed the POST would make the editor claim a save
  // that never happened.
  if (req.method !== 'GET') return;

  var url = new URL(req.url);

  // Draft data is never served from cache. Stale drafts presented as current
  // would be worse than an honest failure, which the page handles.
  if (url.pathname === '/admin/blog/drafts.json') return;

  var isPage = req.mode === 'navigate' ||
               (req.headers.get('accept') || '').indexOf('text/html') !== -1;

  if (isPage) {
    // Network first, so a deploy is picked up immediately and nobody ends up
    // editing in a stale shell. Cache is the offline fallback only.
    event.respondWith(
      fetch(req).then(function (res) {
        var copy = res.clone();
        caches.open(VERSION).then(function (c) { c.put(req, copy); });
        return res;
      }).catch(function () {
        return caches.match(req).then(function (hit) {
          return hit || caches.match('/admin/blog');
        });
      })
    );
    return;
  }

  // Fonts, icons, the manifest: cache first, they don't change between deploys.
  event.respondWith(
    caches.match(req).then(function (hit) {
      return hit || fetch(req).then(function (res) {
        var copy = res.clone();
        caches.open(VERSION).then(function (c) { c.put(req, copy); });
        return res;
      });
    })
  );
});
