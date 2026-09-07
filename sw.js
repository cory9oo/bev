/* BEV service worker. Same shape as HT's: network-first with a same-origin
   cache fallback, so the shell opens offline and the board falls back to its
   localStorage copy WITH ITS AGE. The API is cross-origin and is deliberately
   never cached here - a stale board must come from the app's own cache, where
   it is labelled, not from a service worker that would serve it silently. */
const C = 'bev-v1';
self.addEventListener('install', e => { self.skipWaiting(); });
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(k => Promise.all(k.filter(x => x !== C).map(x => caches.delete(x))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const r = e.request;
  if (r.method !== 'GET') return;
  if (new URL(r.url).origin !== location.origin) return;
  e.respondWith(
    fetch(r, { cache: 'no-cache' }).then(res => {
      if (res && res.status === 200) { const c = res.clone(); caches.open(C).then(k => k.put(r, c)); }
      return res;
    }).catch(() => caches.match(r))
  );
});
