// Utilidades compartidas por captura.html y tablero.html.
// Mapa: Leaflet si está (copia local en /static/vendor/leaflet, que deja instalar.sh; si no, unpkg). Sin internet no
// hay teselas de fondo, pero las calles, el recorrido y los eventos se dibujan igual. Si Leaflet no carga, se usa
// un mapa simple en <canvas> con la misma interfaz (lineas, puntos, ajustar).

const VV = {};

VV.json = async (url, opciones) => {
  const r = await fetch(url, opciones);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
  return d;
};

VV.post = (url, cuerpo, cabeceras) => VV.json(url, {
  method: 'POST', headers: Object.assign({'Content-Type': 'application/json'}, cabeceras || {}),
  body: JSON.stringify(cuerpo || {})
});

VV.cargarScript = (src) => new Promise((ok, mal) => {
  const s = document.createElement('script');
  s.src = src; s.onload = ok; s.onerror = mal;
  document.head.appendChild(s);
});

VV.cargarLeaflet = async () => {
  const fuentes = [['/static/vendor/leaflet/leaflet.js', '/static/vendor/leaflet/leaflet.css'],
                   ['https://unpkg.com/leaflet@1.9.4/dist/leaflet.js', 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css']];
  for (const [js, css] of fuentes) {
    try {
      const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = css; document.head.appendChild(l);
      await VV.cargarScript(js);
      if (window.L) return true;
    } catch (e) { /* siguiente fuente */ }
  }
  return false;
};

VV.color = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

// Mapa con Leaflet ----------------------------------------------------------------------------------------------
class MapaLeaflet {
  constructor(div, centro) {
    this.m = L.map(div, {preferCanvas: true}).setView(centro || [5.5353, -73.3678], 14);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      {maxZoom: 19, attribution: '© OpenStreetMap'}).addTo(this.m);
    this.capas = {};
  }
  capa(nombre) {
    if (this.capas[nombre]) this.capas[nombre].clearLayers();
    else this.capas[nombre] = L.layerGroup().addTo(this.m);
    return this.capas[nombre];
  }
  lineas(nombre, lista) {           // lista: [{puntos:[[lat,lon]...], color, grosor, al_tocar, titulo}]
    const c = this.capa(nombre);
    for (const x of lista) {
      const p = L.polyline(x.puntos, {color: x.color, weight: x.grosor || 3, opacity: x.opacidad || 0.9});
      if (x.titulo) p.bindTooltip(x.titulo);
      if (x.al_tocar) p.on('click', x.al_tocar);
      p.addTo(c);
    }
  }
  puntos(nombre, lista) {           // lista: [{lat, lon, color, radio, titulo}]
    const c = this.capa(nombre);
    for (const x of lista) {
      const p = L.circleMarker([x.lat, x.lon], {radius: x.radio || 6, color: x.borde || '#fff', weight: 1.5,
                                                fillColor: x.color, fillOpacity: 0.95});
      if (x.titulo) p.bindTooltip(x.titulo);
      p.addTo(c);
    }
  }
  centrar(lat, lon) { this.m.panTo([lat, lon], {animate: false}); }
  ajustar(puntos) { if (puntos.length) this.m.fitBounds(puntos, {padding: [20, 20], maxZoom: 17}); }
}

// Mapa simple en canvas (sin Leaflet) ---------------------------------------------------------------------------
class MapaCanvas {
  constructor(div) {
    this.div = div; this.cv = document.createElement('canvas');
    this.cv.style.width = '100%'; this.cv.style.height = '100%'; div.appendChild(this.cv);
    this.datos = {}; this.caja = null;
    const nota = document.createElement('div'); nota.className = 'nota-mapa';
    nota.textContent = 'Mapa simple (sin Leaflet): calles y puntos sin fondo.'; div.appendChild(nota);
    new ResizeObserver(() => this.dibujar()).observe(div);
  }
  lineas(nombre, lista) { this.datos[nombre] = {tipo: 'l', lista}; this.dibujar(); }
  puntos(nombre, lista) { this.datos[nombre] = {tipo: 'p', lista}; this.dibujar(); }
  centrar() { this.dibujar(); }
  ajustar(puntos) {
    if (!puntos.length) return;
    const la = puntos.map(p => p[0]), lo = puntos.map(p => p[1]);
    this.caja = [Math.min(...la), Math.max(...la), Math.min(...lo), Math.max(...lo)];
    this.dibujar();
  }
  dibujar() {
    const r = this.div.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    this.cv.width = r.width * dpr; this.cv.height = r.height * dpr;
    const g = this.cv.getContext('2d'); g.scale(dpr, dpr);
    g.fillStyle = VV.color('--fondo-mapa'); g.fillRect(0, 0, r.width, r.height);
    let caja = this.caja;
    if (!caja) {
      const todos = [];
      for (const d of Object.values(this.datos))
        for (const x of d.lista) d.tipo === 'l' ? todos.push(...x.puntos) : todos.push([x.lat, x.lon]);
      if (!todos.length) return;
      const la = todos.map(p => p[0]), lo = todos.map(p => p[1]);
      caja = [Math.min(...la), Math.max(...la), Math.min(...lo), Math.max(...lo)];
    }
    const k = Math.cos(caja[0] * Math.PI / 180);
    const ancho = Math.max((caja[3] - caja[2]) * k, 1e-4), alto = Math.max(caja[1] - caja[0], 1e-4);
    const esc = Math.min((r.width - 20) / ancho, (r.height - 20) / alto);
    const xy = (lat, lon) => [10 + (lon - caja[2]) * k * esc, r.height - 10 - (lat - caja[0]) * esc];
    for (const d of Object.values(this.datos)) {
      for (const x of d.lista) {
        if (d.tipo === 'l') {
          g.strokeStyle = x.color; g.lineWidth = x.grosor || 2; g.beginPath();
          x.puntos.forEach((p, i) => { const [a, b] = xy(p[0], p[1]); i ? g.lineTo(a, b) : g.moveTo(a, b); });
          g.stroke();
        } else {
          const [a, b] = xy(x.lat, x.lon); g.fillStyle = x.color; g.beginPath();
          g.arc(a, b, x.radio || 5, 0, 2 * Math.PI); g.fill();
        }
      }
    }
  }
}

VV.crearMapa = async (div, centro) => (await VV.cargarLeaflet()) ? new MapaLeaflet(div, centro) : new MapaCanvas(div);

VV.texto = (v, sufijo, dec) => (v === null || v === undefined) ? '—' :
  (typeof v === 'number' ? v.toFixed(dec === undefined ? 1 : dec) : v) + (sufijo || '');

VV.escapar = (s) => String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g,
  c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
