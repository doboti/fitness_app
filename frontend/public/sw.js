// Service Worker: offline app shell. Az /api hívásokat soha nem cache-eljük (azokat a Dexie + szinkron kezeli).
const CACHE = 'workout-shell-__BUILD_ID__';
const SHELL = ['/', '/index.html', '__PRECACHE__'];
const OPTIONAL = ['/manifest.webmanifest', '/icons/icon.svg', '/icons/icon-192.png'];

self.addEventListener('install', (event) => {
    // Csak az app shell kötelező; egy hiányzó ikon miatt ne bukjon el az egész telepítés.
    event.waitUntil(caches.open(CACHE)
        .then((cache) => cache.addAll(SHELL).then(() => Promise.allSettled(OPTIONAL.map((url) => cache.add(url)))))
        .then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
            .then(() => self.clients.claim()),
    );
});

self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);
    if (request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;

    // Navigáció: hálózat először (friss verzió), offline a cache-elt index.html.
    if (request.mode === 'navigate') {
        event.respondWith(
            fetch(request)
                .then((response) => {
                    const copy = response.clone();
                    caches.open(CACHE).then((cache) => cache.put('/index.html', copy));
                    return response;
                })
                .catch(() => caches.match('/index.html')),
        );
        return;
    }

    // Statikus fájlok (a Vite hash-elt assetjei): cache először, háttérben frissítve.
    event.respondWith(
        caches.match(request).then((cached) => {
            const network = fetch(request)
                .then((response) => {
                    if (response.ok) {
                        const copy = response.clone();
                        caches.open(CACHE).then((cache) => cache.put(request, copy));
                    }
                    return response;
                })
                .catch(() => cached);
            return cached || network;
        }),
    );
});
