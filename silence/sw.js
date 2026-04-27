'use strict';

// __CACHE_VERSION__ is replaced by the Vite plugin at build time with the bundle hash.
const CACHE = 'soj-__CACHE_VERSION__';

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const { request } = e;
  const url = new URL(request.url);

  // Auth endpoints — never cache (tokens, login state)
  if (url.pathname.startsWith('/auth/')) return;

  // Hashed assets (content-addressed) — cache-first, safe indefinitely
  if (url.pathname.startsWith('/silence/assets/')) {
    e.respondWith(
      caches.match(request).then(cached => cached ||
        fetch(request).then(res => {
          if (res.ok) caches.open(CACHE).then(c => c.put(request, res.clone()));
          return res;
        })
      )
    );
    return;
  }

  // API data (RSS feed, IGDB metadata) — network-first, cache as offline fallback
  if (url.pathname.startsWith('/rss/') || url.pathname.startsWith('/igdb/')) {
    e.respondWith(
      fetch(request)
        .then(res => {
          if (res.ok) caches.open(CACHE).then(c => c.put(request, res.clone()));
          return res;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Navigation — network-first, fall back to cached SPA entry point
  if (request.mode === 'navigate') {
    e.respondWith(
      fetch(request)
        .then(res => {
          if (res.ok) caches.open(CACHE).then(c => c.put(request, res.clone()));
          return res;
        })
        .catch(() => caches.match('/silence/') || caches.match(request))
    );
    return;
  }
});
