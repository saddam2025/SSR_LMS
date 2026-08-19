const CACHE = 'ragab-seddik-static-v96-wheel-typography1';
const STATIC_ASSETS = [
  '/static/style.css',
  '/static/protected-content.js',
  '/static/quiz-timer.js',
  '/static/pwa-register.js',
  '/static/lesson-experience.js',
  '/static/admin-interactive.js',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/offline.html'
];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(STATIC_ASSETS)));
  self.skipWaiting();
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(fetch(req).then(response => {
      const copy = response.clone();
      caches.open(CACHE).then(cache => cache.put(req, copy));
      return response;
    }).catch(() => caches.match(req)));
    return;
  }
  event.respondWith(fetch(req).catch(() => {
    if (req.mode === 'navigate') return caches.match('/static/offline.html');
    return Response.error();
  }));
});
