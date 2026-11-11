// Utilidades compartidas por captura.html, tablero.html y entrar.html.
// Mapa: Leaflet si está (copia local en /static/vendor/leaflet, que deja instalar.sh; si no, unpkg). Sin internet no
// hay teselas de fondo, pero las calles, el recorrido y los huecos se dibujan igual. Si Leaflet no carga, se usa
// un mapa simple en <canvas> con la misma interfaz (lineas, puntos, mostrar, ajustar).

const VV = {};

VV.json = async (url, opciones) => {
  const r = await fetch(url, Object.assign({credentials: 'same-origin'}, opciones || {}));
  if (r.status === 401 && !['/entrar', '/marcar', '/sync'].includes(location.pathname)) {
    location.href = '/entrar?siguiente=' + encodeURIComponent(location.pathname);
    throw new Error('Debe entrar');
  }
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(d.error || ('HTTP ' + r.status)); e.datos = d; e.codigo = r.status; throw e; }
  return d;
};

VV.post = (url, cuerpo) => VV.json(url, {method: 'POST', headers: {'Content-Type': 'application/json'},
                                         body: JSON.stringify(cuerpo || {})});

VV.cargarScript = (src) => new Promise((ok, mal) => {
  const s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = mal; document.head.appendChild(s);
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
VV.COLOR_ESTADO = {detectado: '--est-detectado', verificado: '--est-verificado', reparado: '--est-reparado',
                   descartado: '--est-descartado'};

// Mapa con Leaflet ----------------------------------------------------------------------------------------------
class MapaLeaflet {
  constructor(div, centro) {
    this.m = L.map(div, {preferCanvas: true, zoomControl: true}).setView(centro || [5.5353, -73.3678], 14);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
      {maxZoom: 19, attribution: '© OpenStreetMap'}).addTo(this.m);
    this.capas = {}; this.ocultas = new Set();
  }
  capa(nombre) {
    if (this.capas[nombre]) this.capas[nombre].clearLayers();
    else { this.capas[nombre] = L.layerGroup(); if (!this.ocultas.has(nombre)) this.capas[nombre].addTo(this.m); }
    return this.capas[nombre];
  }
  mostrar(nombre, visible) {
    visible ? this.ocultas.delete(nombre) : this.ocultas.add(nombre);
    const c = this.capas[nombre]; if (!c) return;
    visible ? c.addTo(this.m) : this.m.removeLayer(c);
  }
  lineas(nombre, lista) {           // [{puntos:[[lat,lon]...], color, grosor, opacidad, al_tocar, titulo}]
    const c = this.capa(nombre);
    for (const x of lista) {
      const p = L.polyline(x.puntos, {color: x.color, weight: x.grosor || 3, opacity: x.opacidad || 0.9});
      if (x.titulo) p.bindTooltip(x.titulo, {sticky: true});
      if (x.al_tocar) p.on('click', x.al_tocar);
      p.addTo(c);
    }
  }
  puntos(nombre, lista) {           // [{lat, lon, color, radio, titulo, al_tocar}]
    const c = this.capa(nombre);
    for (const x of lista) {
      const p = L.circleMarker([x.lat, x.lon], {radius: x.radio || 6, color: x.borde || '#ffffff', weight: 1.5,
                                                fillColor: x.color, fillOpacity: 0.95});
      if (x.titulo) p.bindTooltip(x.titulo);
      if (x.al_tocar) p.on('click', x.al_tocar);
      p.addTo(c);
    }
  }
  centrar(lat, lon, zoom) { zoom ? this.m.setView([lat, lon], zoom) : this.m.panTo([lat, lon], {animate: false}); }
  ajustar(puntos) { if (puntos.length) this.m.fitBounds(puntos, {padding: [24, 24], maxZoom: 17}); }
  redimensionar() { this.m.invalidateSize(); }
}

// Mapa simple en canvas (sin Leaflet) ---------------------------------------------------------------------------
class MapaCanvas {
  constructor(div) {
    this.div = div; this.cv = document.createElement('canvas');
    this.cv.style.width = '100%'; this.cv.style.height = '100%'; div.appendChild(this.cv);
    this.datos = {}; this.caja = null; this.ocultas = new Set();
    const nota = document.createElement('div'); nota.className = 'nota-mapa';
    nota.textContent = 'Mapa simple (sin Leaflet): calles y puntos sin fondo.'; div.appendChild(nota);
    new ResizeObserver(() => this.dibujar()).observe(div);
  }
  lineas(nombre, lista) { this.datos[nombre] = {tipo: 'l', lista}; this.dibujar(); }
  puntos(nombre, lista) { this.datos[nombre] = {tipo: 'p', lista}; this.dibujar(); }
  mostrar(nombre, visible) { visible ? this.ocultas.delete(nombre) : this.ocultas.add(nombre); this.dibujar(); }
  centrar() { this.dibujar(); }
  redimensionar() { this.dibujar(); }
  ajustar(puntos) {
    if (!puntos.length) return;
    const la = puntos.map(p => p[0]), lo = puntos.map(p => p[1]);
    this.caja = [Math.min(...la), Math.max(...la), Math.min(...lo), Math.max(...lo)];
    this.dibujar();
  }
  dibujar() {
    const r = this.div.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    if (!r.width) return;
    this.cv.width = r.width * dpr; this.cv.height = r.height * dpr;
    const g = this.cv.getContext('2d'); g.scale(dpr, dpr);
    g.fillStyle = VV.color('--fondo-mapa'); g.fillRect(0, 0, r.width, r.height);
    const visibles = Object.entries(this.datos).filter(([n]) => !this.ocultas.has(n)).map(([, d]) => d);
    let caja = this.caja;
    if (!caja) {
      const todos = [];
      for (const d of visibles) for (const x of d.lista) d.tipo === 'l' ? todos.push(...x.puntos) : todos.push([x.lat, x.lon]);
      if (!todos.length) return;
      const la = todos.map(p => p[0]), lo = todos.map(p => p[1]);
      caja = [Math.min(...la), Math.max(...la), Math.min(...lo), Math.max(...lo)];
    }
    const k = Math.cos(caja[0] * Math.PI / 180);
    const ancho = Math.max((caja[3] - caja[2]) * k, 1e-4), alto = Math.max(caja[1] - caja[0], 1e-4);
    const esc = Math.min((r.width - 20) / ancho, (r.height - 20) / alto);
    const xy = (lat, lon) => [10 + (lon - caja[2]) * k * esc, r.height - 10 - (lat - caja[0]) * esc];
    for (const d of visibles) for (const x of d.lista) {
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

VV.crearMapa = async (div, centro) => (await VV.cargarLeaflet()) ? new MapaLeaflet(div, centro) : new MapaCanvas(div);

VV.texto = (v, sufijo, dec) => (v === null || v === undefined) ? '—' :
  (typeof v === 'number' ? v.toFixed(dec === undefined ? 1 : dec) : v) + (sufijo || '');

VV.escapar = (s) => String(s === null || s === undefined ? '' : s).replace(/[&<>"']/g,
  c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

VV.fecha = (ts) => {                 // UTC ISO → hora de Tunja (UTC-5) legible
  if (!ts) return '—';
  const d = new Date(ts.endsWith('Z') ? ts : ts + 'Z');
  if (isNaN(d)) return ts;
  return d.toLocaleString('es-CO', {timeZone: 'America/Bogota', day: '2-digit', month: 'short', hour: '2-digit',
                                    minute: '2-digit'});
};

VV.aviso = (texto, tipo) => {        // mensaje flotante breve
  let c = document.getElementById('avisos');
  if (!c) { c = document.createElement('div'); c.id = 'avisos'; document.body.appendChild(c); }
  const a = document.createElement('div'); a.className = 'toast ' + (tipo || ''); a.textContent = texto;
  c.appendChild(a); setTimeout(() => a.classList.add('sale'), 1800); setTimeout(() => a.remove(), 2300);
};

VV.usuario = async (contenedor) => {  // muestra quién está y el botón Salir
  const r = await VV.json('/api/yo');
  const u = r.usuario;
  if (contenedor && u) {
    contenedor.innerHTML = '<span class="persona">' + VV.escapar(u.nombre || u.usuario) + '</span>' +
      '<span class="rol rol-' + u.rol + '">' + ({editor: 'Editor', alcaldia: 'Alcaldía', docente: 'Docente'}[u.rol]) +
      '</span>' + (u.usuario === 'local' ? '' : '<button class="enlace" id="b-salir">Salir</button>');
    const b = document.getElementById('b-salir');
    if (b) b.onclick = async () => { await VV.post('/api/salir'); location.href = '/entrar'; };
  }
  return r;
};

// Navegación común (un solo sistema): se pone después de la marca en la barra superior.
VV.nav = (actual, rol) => {
  const barra = document.querySelector('.barra .marca');
  if (!barra) return;
  const paginas = [['campo', 'Campo', '/captura', 'editor'], ['sesiones', 'Sesiones', '/sesiones', 'editor'],
                   ['dataset', 'Dataset', '/dataset', 'editor'], ['tablero', 'Tablero', '/tablero', ''],
                   ['demo', 'Demo', '/demo', 'editor']];
  const n = document.createElement('nav'); n.className = 'nav';
  n.innerHTML = paginas.filter(p => !p[3] || rol === p[3]).map(([id, t, h]) =>
    '<a href="' + h + '"' + (id === actual ? ' class="on" aria-current="page"' : '') + '>' + t + '</a>').join('');
  barra.after(n);
};
