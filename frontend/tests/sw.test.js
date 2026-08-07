import { describe, it, expect, vi } from 'vitest';
// sw.js runs in a ServiceWorkerGlobalScope, which jsdom does not provide. Rather
// than mock a whole worker, evaluate the source with the handful of globals it
// actually touches and capture the listener it registers. `?raw` keeps this
// reading the shipped file, so the test cannot drift from what deploys.
import source from '../sw.js?raw';

const ORIGIN = 'https://ludo.tezcat.fr';

function loadWorker({ cacheContents = {} } = {}) {
  const listeners = {};
  const self = {
    addEventListener: (type, fn) => { listeners[type] = fn; },
    clients: { claim: vi.fn() },
  };
  const cache = { put: vi.fn() };
  const caches = {
    open: vi.fn(() => Promise.resolve(cache)),
    keys: vi.fn(() => Promise.resolve([])),
    delete: vi.fn(),
    // The real caches.match resolves a relative string against the worker's
    // scope, so '/' and the absolute origin URL are the same entry. It resolves
    // to undefined for a miss rather than rejecting — which is exactly what the
    // fallback below has to cope with.
    match: vi.fn(key => {
      const raw = typeof key === 'string' ? key : key.url;
      return Promise.resolve(cacheContents[new URL(raw, ORIGIN).href]);
    }),
  };
  const fetchMock = vi.fn(() => Promise.reject(new Error('offline')));
  // eslint-disable-next-line no-new-func
  new Function('self', 'caches', 'fetch', source)(self, caches, fetchMock);
  return { listeners, caches, fetchMock };
}

function navigateTo(listeners, url) {
  let responded;
  listeners.fetch({
    request: { url, method: 'GET', mode: 'navigate' },
    respondWith: p => { responded = p; },
  });
  return responded;
}

describe('service worker offline navigation fallback', () => {
  const origin = ORIGIN;

  it('serves the cached app shell when the network is unavailable', async () => {
    const shell = { body: 'index.html' };
    const { listeners } = loadWorker({ cacheContents: { [`${origin}/`]: shell } });

    await expect(navigateTo(listeners, `${origin}/game/zelda`)).resolves.toBe(shell);
  });

  it('falls back to the requested page when the shell is not cached', async () => {
    // Regression guard. caches.match returns a promise, which is always truthy,
    // so `caches.match('/') || caches.match(request)` silently resolved to
    // undefined here — and respondWith(undefined) is a network error, meaning
    // the offline fallback never worked at all.
    const page = { body: 'deep link' };
    const { listeners } = loadWorker({ cacheContents: { [`${origin}/game/zelda`]: page } });

    await expect(navigateTo(listeners, `${origin}/game/zelda`)).resolves.toBe(page);
  });

  it('does not intercept auth requests', () => {
    const { listeners } = loadWorker();
    expect(navigateTo(listeners, `${origin}/auth/login`)).toBeUndefined();
  });

  it('does not intercept the SSE resolution stream', () => {
    const { listeners } = loadWorker();
    expect(navigateTo(listeners, `${origin}/games/resolution-stream`)).toBeUndefined();
  });
});
