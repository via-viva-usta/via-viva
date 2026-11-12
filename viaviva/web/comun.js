// Utilidades compartidas por todas las pantallas de la app local.
// Mapa: MapLibre (copia local en /static/vendor/maplibre, que dejan los instaladores; si no, jsDelivr) con el fondo
// de OpenFreeMap, como el tablero en línea; el trabajador sw.js guarda las teselas vistas para usarlas sin internet.
// Debajo van SIEMPRE las calles de la base local (/api/calles): sin red el mapa muestra las calles de Tunja igual. Sin
// WebGL, un mapa simple en <canvas> con la misma interfaz (lineas, puntos, mostrar, ajustar) y las mismas calles.
// Estilo: marca.css y tema.js de la web de Dany (oscuro por defecto, ◐ cambia a claro; misma llave vv_tema).

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

// MapLibre 6.17 (el mismo del tablero en línea de Dany): copia local que dejan los instaladores; si no, jsDelivr.
VV.cargarMapLibre = async () => {
  if (window.maplibregl) return true;
  for (const [js, css] of [['/static/vendor/maplibre/maplibre-gl.mjs', '/static/vendor/maplibre/maplibre-gl.css'],
                           ['https://cdn.jsdelivr.net/npm/maplibre-gl@6.17.0/dist/maplibre-gl.mjs',
                            'https://cdn.jsdelivr.net/npm/maplibre-gl@6.17.0/dist/maplibre-gl.css']]) {
    try {
      window.maplibregl = await import(js);
      const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = css; document.head.appendChild(l);
      return true;
    } catch (e) { /* siguiente fuente */ }
  }
  return false;
};

VV.color = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
VV.oscuro = () => document.documentElement.dataset.theme !== 'light';
VV.COLOR_ESTADO = {detectado: '--est-detectado', verificado: '--est-verificado', reparado: '--est-reparado',
                   descartado: '--est-descartado'};

// Calles de Tunja para el fondo del mapa (una sola descarga por página)
VV._calles = null;
VV.calles = () => VV._calles || (VV._calles = fetch('/api/calles').then(r => r.ok ? r.json() : {calles: []})
  .then(d => d.calles || []).catch(() => []));
VV.colorCalle = (tipo) => {
  const o = VV.oscuro();
  return tipo <= 1 ? (o ? '#5a5a5a' : '#9a9a9a') : tipo <= 3 ? (o ? '#3d3d3d' : '#b9b9b9') : (o ? '#2a2a2a' : '#d4d4d4');
};
// Fondo: OpenFreeMap (OpenStreetMap, sin clave ni límite; el mismo del tablero en línea). Sin internet: fondo propio
// con las calles de la base local. CARTO dejó de servir teselas sin clave (marca de agua «API KEY REQUIRED», 12-nov).
VV.ESTILO = () => 'https://tiles.openfreemap.org/styles/' + (VV.oscuro() ? 'dark' : 'positron');
VV.ESTILO_LOCAL = () => ({version: 8, sources: {}, layers: [{id: 'fondo', type: 'background',
  paint: {'background-color': VV.oscuro() ? '#0c0c0c' : '#f3f3f0'}}]});
VV.ATRIBUCION = '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> · ' +
  '<a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a>';

// Mapa con MapLibre: cada capa con nombre es una fuente GeoJSON (líneas o puntos) ---------------------------------
const VACIO = {type: 'FeatureCollection', features: []};
class MapaML {
  constructor(div, centro) {
    this.div = div; this.datos = {}; this.ocultas = new Set(); this.toques = {}; this.local = false;
    this.nota = document.createElement('div'); this.nota.className = 'nota-mapa oculto';
    this.nota.textContent = 'Sin internet: fondo con las calles de la base local'; div.appendChild(this.nota);
    this.m = new maplibregl.Map({container: div, style: navigator.onLine === false ? VV.ESTILO_LOCAL() : VV.ESTILO(),
      center: centro ? [centro[1], centro[0]] : [-73.3678, 5.5353], zoom: 14, attributionControl: false,
      cooperativeGestures: matchMedia('(pointer: coarse)').matches});
    this.m.addControl(new maplibregl.AttributionControl({compact: true}));
    this.m.addControl(new maplibregl.NavigationControl({showCompass: false}), 'top-right');
    this.local = navigator.onLine === false; this.estiloOk = false;
    this.m.on('style.load', () => { this.estiloOk = true; this.ponerCapas(); });
    this.m.on('error', (e) => {                      // sin red, el estilo de OpenFreeMap no llega → fondo local
      if (!this.estiloOk && !this.local) this.usarLocal();
    });
    setTimeout(() => { if (!this.estiloOk) this.usarLocal(); }, 8000);
    window.addEventListener('online', () => { if (this.local) { this.local = false; this.estiloOk = false; this.m.setStyle(VV.ESTILO()); } });
    document.addEventListener('vv-tema', () => this.m.setStyle(this.local ? VV.ESTILO_LOCAL() : VV.ESTILO()));
    this.flotante = new maplibregl.Popup({closeButton: false, closeOnClick: false, offset: 10, className: 'pop-corto'});
    new ResizeObserver(() => this.m.resize()).observe(div);
  }
  usarLocal() {
    if (this.local) return;
    this.local = true; this.estiloOk = false; this.nota.classList.remove('oculto'); this.m.setStyle(VV.ESTILO_LOCAL());
  }
  async ponerCapas() {
    const m = this.m;
    this.nota.classList.toggle('oculto', !this.local);
    const calles = await VV.calles();
    if (!m.getSource('calles')) {
      m.addSource('calles', {type: 'geojson', attribution: this.local ? VV.ATRIBUCION : '', data: {type: 'FeatureCollection', features: calles.map(([t, pts]) => ({
        type: 'Feature', properties: {t}, geometry: {type: 'LineString', coordinates: pts.map(p => [p[1], p[0]])}}))}});
      m.addLayer({id: 'calles', type: 'line', source: 'calles', layout: {'line-cap': 'round', 'line-join': 'round'},
        paint: {'line-color': ['match', ['get', 't'], 1, VV.colorCalle(1), 2, VV.colorCalle(2), 3, VV.colorCalle(3), VV.colorCalle(4)],
                'line-width': ['interpolate', ['linear'], ['zoom'], 11, ['match', ['get', 't'], 1, 1.5, 0.4],
                               16, ['match', ['get', 't'], 1, 6, 2, 4, 3, 3, 2]],
                'line-opacity': this.local ? 1 : 0.35}});
    }
    for (const nombre of Object.keys(this.datos)) this.ponerCapa(nombre);
  }
  ponerCapa(nombre) {
    const d = this.datos[nombre], m = this.m;
    if (!m.getSource('calles')) return;          // ponerCapas las agrega cuando el estilo esté listo
    const id = 'd-' + nombre, src = m.getSource(id);
    if (src) src.setData(d.geo);
    else {
      m.addSource(id, {type: 'geojson', data: d.geo});
      if (d.tipo === 'l') m.addLayer({id, type: 'line', source: id, layout: {'line-cap': 'round', 'line-join': 'round'},
        paint: {'line-color': ['get', 'color'], 'line-width': ['get', 'grosor'], 'line-opacity': ['get', 'opacidad']}});
      else m.addLayer({id, type: 'circle', source: id, paint: {'circle-color': ['get', 'color'], 'circle-radius': ['get', 'radio'],
        'circle-stroke-color': ['get', 'borde'], 'circle-stroke-width': 1.5}});
      m.on('mousemove', id, (e) => {
        const f = e.features[0]; m.getCanvas().style.cursor = this.toques[id + ':' + f.properties.i] ? 'pointer' : '';
        if (f.properties.titulo) this.flotante.setLngLat(e.lngLat).setHTML(VV.escapar(f.properties.titulo)).addTo(m);
      });
      m.on('mouseleave', id, () => { m.getCanvas().style.cursor = ''; this.flotante.remove(); });
      m.on('click', id, (e) => { const f = this.toques[id + ':' + e.features[0].properties.i]; if (f) f(); });
    }
    m.setLayoutProperty(id, 'visibility', this.ocultas.has(nombre) ? 'none' : 'visible');
  }
  lineas(nombre, lista) {           // [{puntos:[[lat,lon]...], color, grosor, opacidad, al_tocar, titulo}]
    const id = 'd-' + nombre;
    this.datos[nombre] = {tipo: 'l', geo: {type: 'FeatureCollection', features: lista.filter(x => x.puntos.length > 1).map((x, i) => {
      if (x.al_tocar) this.toques[id + ':' + i] = x.al_tocar;
      return {type: 'Feature', properties: {i, color: x.color, grosor: x.grosor || 3, opacidad: x.opacidad || 0.9,
        titulo: x.titulo || ''}, geometry: {type: 'LineString', coordinates: x.puntos.map(p => [p[1], p[0]])}};
    })}};
    this.ponerCapa(nombre);
  }
  puntos(nombre, lista) {           // [{lat, lon, color, radio, titulo, al_tocar, borde}]
    const id = 'd-' + nombre;
    this.datos[nombre] = {tipo: 'p', geo: {type: 'FeatureCollection', features: lista.map((x, i) => {
      if (x.al_tocar) this.toques[id + ':' + i] = x.al_tocar;
      return {type: 'Feature', properties: {i, color: x.color, radio: x.radio || 6, borde: x.borde || '#ffffff',
        titulo: x.titulo || ''}, geometry: {type: 'Point', coordinates: [x.lon, x.lat]}};
    })}};
    this.ponerCapa(nombre);
  }
  mostrar(nombre, visible) {
    visible ? this.ocultas.delete(nombre) : this.ocultas.add(nombre);
    if (this.m.getLayer('d-' + nombre)) this.m.setLayoutProperty('d-' + nombre, 'visibility', visible ? 'visible' : 'none');
  }
  centrar(lat, lon, zoom) { zoom ? this.m.jumpTo({center: [lon, lat], zoom}) : this.m.easeTo({center: [lon, lat], duration: 400}); }
  ajustar(puntos) {
    if (!puntos.length) return;
    const b = puntos.reduce((b, p) => b.extend([p[1], p[0]]), new maplibregl.LngLatBounds([puntos[0][1], puntos[0][0]],
                                                                                              [puntos[0][1], puntos[0][0]]));
    this.m.fitBounds(b, {padding: 30, maxZoom: 17, duration: 0});
  }
  redimensionar() { this.m.resize(); }
}

// Mapa simple en canvas (sin Leaflet) ---------------------------------------------------------------------------
class MapaCanvas {
  constructor(div) {
    this.div = div; this.cv = document.createElement('canvas');
    this.cv.style.width = '100%'; this.cv.style.height = '100%'; div.appendChild(this.cv);
    this.datos = {}; this.caja = null; this.ocultas = new Set(); this.calles = [];
    const nota = document.createElement('div'); nota.className = 'nota-mapa';
    nota.textContent = 'Mapa simple: calles de la base local, sin fondo.'; div.appendChild(nota);
    new ResizeObserver(() => this.dibujar()).observe(div);
    VV.calles().then(c => { this.calles = c; this.dibujar(); });
    document.addEventListener('vv-tema', () => this.dibujar());
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
      if (!todos.length) todos.push([5.5253, -73.3778], [5.5453, -73.3578]);   // centro de Tunja
      const la = todos.map(p => p[0]), lo = todos.map(p => p[1]);
      caja = [Math.min(...la), Math.max(...la), Math.min(...lo), Math.max(...lo)];
    }
    const k = Math.cos(caja[0] * Math.PI / 180);
    const ancho = Math.max((caja[3] - caja[2]) * k, 1e-4), alto = Math.max(caja[1] - caja[0], 1e-4);
    const esc = Math.min((r.width - 20) / ancho, (r.height - 20) / alto);
    const xy = (lat, lon) => [10 + (lon - caja[2]) * k * esc, r.height - 10 - (lat - caja[0]) * esc];
    for (const [tipo, pts] of this.calles) {
      g.strokeStyle = VV.colorCalle(tipo); g.lineWidth = tipo <= 1 ? 2 : 1; g.beginPath();
      pts.forEach((p, i) => { const [a, b] = xy(p[0], p[1]); i ? g.lineTo(a, b) : g.moveTo(a, b); });
      g.stroke();
    }
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

VV.crearMapa = async (div, centro) => {
  try { if (await VV.cargarMapLibre()) return new MapaML(div, centro); } catch (e) { /* sin WebGL: mapa simple */ }
  return new MapaCanvas(div);
};

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

// Navegación común (un solo sistema, como la barra de la web de Dany): logo · secciones · ◐
VV.nav = (actual, rol) => {
  const barra = document.querySelector('.barra .marca');
  if (!barra || document.querySelector('.barra nav.nav')) return;
  const paginas = [['campo', 'Campo', '/captura', 'editor'], ['sesiones', 'Sesiones', '/sesiones', 'editor'],
                   ['dataset', 'Dataset', '/dataset', 'editor'], ['tablero', 'Tablero', '/tablero', ''],
                   ['demo', 'Demo', '/demo', 'editor']];
  const n = document.createElement('nav'); n.className = 'nav'; n.setAttribute('aria-label', 'Secciones');
  n.innerHTML = paginas.filter(p => !p[3] || rol === p[3]).map(([id, t, h]) =>
    '<a href="' + h + '"' + (id === actual ? ' class="on" aria-current="page"' : '') + '>' + t + '</a>').join('');
  barra.after(n);
};

// Tema oscuro / claro (misma llave que la web en línea: vv_tema)
VV.cambiarTema = () => {
  const nuevo = VV.oscuro() ? 'light' : 'dark';
  document.documentElement.dataset.theme = nuevo;
  try { localStorage.setItem('vv_tema', nuevo); } catch (e) { /* sin almacenamiento */ }
  document.dispatchEvent(new Event('vv-tema'));
};
VV.botonTema = () => {
  const barra = document.querySelector('.barra');
  if (!barra || document.getElementById('b-tema')) return;
  const b = document.createElement('button');
  b.id = 'b-tema'; b.type = 'button'; b.className = 'icono'; b.textContent = '◐';
  b.title = 'Modo oscuro / claro'; b.setAttribute('aria-label', 'Cambiar entre modo oscuro y claro');
  b.onclick = VV.cambiarTema;
  const cuenta = barra.querySelector('.cuenta');
  cuenta ? barra.insertBefore(b, cuenta) : barra.appendChild(b);
};

// App instalable y ventana propia: caché del mapa (sw.js) y latido para que `viaviva app` sepa que la ventana sigue
VV.arranque = () => {
  VV.botonTema();
  if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('/sw.js').catch(() => {});
  try {
    if (new URLSearchParams(location.search).has('app')) sessionStorage.setItem('vv_app', '1');
    if (sessionStorage.getItem('vv_app')) {
      const latir = () => fetch('/api/latido', {method: 'POST'}).catch(() => {});
      latir(); setInterval(latir, 5000);
    }
  } catch (e) { /* sin sessionStorage */ }
};
document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', VV.arranque) : VV.arranque();
