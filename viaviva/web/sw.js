// VÍA VIVA · trabajador de la app local (solo en http://localhost o HTTPS: el navegador no lo permite en http://IP).
// 1) Mapa de OpenFreeMap (estilo, teselas, sprites, letras): primero la caché, así lo ya visto sigue sin internet.
// 2) Archivos de la app (/static, marca, fuentes, calles): de la red y, si no hay, de la caché.
// La API (/api, salvo /api/calles) nunca se guarda: siempre es el dato en vivo.
const TESELAS = 'vv-teselas-2', APP = 'vv-app-2', MAX_TESELAS = 6000;

self.addEventListener('install', (e) => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil((async () => {
  for (const k of await caches.keys()) if (![TESELAS, APP].includes(k)) await caches.delete(k);
  await self.clients.claim();
})()));

async function recortar() {
  const c = await caches.open(TESELAS), llaves = await c.keys();
  for (let i = 0; i < llaves.length - MAX_TESELAS; i++) await c.delete(llaves[i]);
}

self.addEventListener('fetch', (e) => {
  const u = new URL(e.request.url);
  if (e.request.method !== 'GET') return;
  if (u.hostname === 'tiles.openfreemap.org') {
    e.respondWith((async () => {
      const c = await caches.open(TESELAS), guardada = await c.match(e.request);
      if (guardada) return guardada;
      const r = await fetch(e.request);
      if (r.ok || r.type === 'opaque') { c.put(e.request, r.clone()); if (Math.random() < .02) recortar(); }
      return r;
    })());
    return;
  }
  const propia = u.origin === self.location.origin;
  const estatico = propia && (u.pathname.startsWith('/static/') || u.pathname.startsWith('/fuentes/') ||
    ['/marca.css', '/tema.js', '/api/calles', '/manifest.webmanifest'].includes(u.pathname));
  // (el estilo de OpenFreeMap trae la URL de las teselas «planet» que cambia con cada versión: cache-first está bien)
  if (!estatico) return;
  e.respondWith((async () => {
    const c = await caches.open(APP);
    try { const r = await fetch(e.request); if (r.ok) c.put(e.request, r.clone()); return r; }
    catch (err) { const g = await c.match(e.request); if (g) return g; throw err; }
  })());
});
