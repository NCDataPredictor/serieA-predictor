// Worker único de NCData Predictor (raíz, alcance "/"): avisos de OneSignal para todo el sitio (NBA y Serie A)
// + copia sin conexión. Red primero: los datos cambian varias veces al día, así que con conexión nunca se sirve
// una versión vieja; sin conexión se usa la última copia de las páginas.
importScripts("https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.sw.js");
const CACHE = "ncdata-v1";
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
