// Service worker de la app NCData Predictor (instalable). Red primero: los datos cambian varias veces al día,
// así que nunca se sirve una versión vieja si hay conexión; sin conexión se usa la última copia de las páginas.
// La NBA (/nba/) tiene su propio worker (OneSignal) con alcance /nba/, que tiene prioridad allí.
const CACHE = "ncdata-v1";
self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", e => {
  const r = e.request;
  if (r.method !== "GET" || new URL(r.url).origin !== location.origin) return;
  e.respondWith(fetch(r).then(res => {
    if (res.ok && (r.mode === "navigate" || /\.(json|svg|png)$/.test(new URL(r.url).pathname))) {
      const copia = res.clone(); caches.open(CACHE).then(c => c.put(r, copia));
    }
    return res;
  }).catch(() => caches.match(r)));
});
