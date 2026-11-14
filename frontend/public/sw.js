/*
 * Service worker básico de la PWA.
 *
 * - La API (otro origen, o rutas /api/) nunca se cachea: siempre va a la red.
 * - Navegación (abrir una ruta de la app): red primero; sin conexión, el index.html
 *   guardado, y React Router resuelve la ruta.
 * - Archivos estáticos del mismo origen (JS/CSS con hash, íconos): caché primero.
 *
 * Al cambiar la lógica de este archivo, sube VERSION para descartar el caché anterior.
 */
const VERSION = 'v1';
const CACHE = `parqueadero-${VERSION}`;
const SHELL = ['/', '/index.html', '/manifest.webmanifest', '/favicon.svg', '/icons/icon-192.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((claves) => Promise.all(claves.filter((c) => c !== CACHE).map((c) => caches.delete(c))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/')) return;

  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((respuesta) => {
          const copia = respuesta.clone();
          caches.open(CACHE).then((cache) => cache.put('/index.html', copia));
          return respuesta;
        })
        .catch(() => caches.match('/index.html')),
    );
    return;
  }

  event.respondWith(
    caches.match(request).then(
      (guardada) =>
        guardada ||
        fetch(request).then((respuesta) => {
          if (respuesta.ok) {
            const copia = respuesta.clone();
            caches.open(CACHE).then((cache) => cache.put(request, copia));
          }
          return respuesta;
        }),
    ),
  );
});
