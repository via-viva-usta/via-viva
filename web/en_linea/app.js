// VÍA VIVA · tablero en línea (estático, Netlify). Lee de Supabase con la clave pública + sesión (RLS por rol).
// ?demo=1 → datos INVENTADOS en el navegador para ver el diseño sin cuenta (con aviso).  ?kiosco=1 → pantalla fija.
import * as maplibregl from 'https://cdn.jsdelivr.net/npm/maplibre-gl@6.17.0/dist/maplibre-gl.mjs';
import Chart from 'https://cdn.jsdelivr.net/npm/chart.js@4.6.1/auto/+esm';
import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.119.0/+esm';

const $ = (id) => document.getElementById(id);
const P = new URLSearchParams(location.search);
const DEMO = P.has('demo'), KIOSCO = P.has('kiosco');
const CFG = window.VIAVIVA || {};
const ESTADOS = ['detectado', 'verificado', 'reparado', 'descartado'];
const NOMBRE = {detectado: 'Detectado', verificado: 'Verificado', reparado: 'Reparado', descartado: 'Descartado'};
const CORTES = [0.2, 0.4, 0.6, 0.8];
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const fecha = (ts) => ts ? new Date(ts).toLocaleString('es-CO', {timeZone: 'America/Bogota', day: '2-digit', month: 'short',
  hour: '2-digit', minute: '2-digit'}) : '—';
let sb = null, yo = null, mapa = null, tramos = null, huecos = [], riesgo = [], corrida = null, graficos = {};

// ------------------------------------------------------------------ tema y pantalla fija
const temaGuardado = (() => { try { return localStorage.getItem('vv_tema'); } catch (e) { return null; } })();
document.documentElement.dataset.theme = temaGuardado || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
$('b-tema').onclick = () => {
  const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem('vv_tema', t); } catch (e) {}
  if (mapa) mapa.setStyle(estiloMapa(), {diff: false});
};
$('b-kiosco').onclick = () => { const u = new URL(location); u.searchParams.set('kiosco', '1'); location = u; };
if (KIOSCO) {
  document.body.classList.add('kiosco');
  document.addEventListener('click', () => document.documentElement.requestFullscreen?.().catch(() => {}), {once: true});
  navigator.wakeLock?.request('screen').catch(() => {});
}
for (const b of document.querySelectorAll('[data-cerrar]')) b.onclick = () => b.closest('dialog').close();

// ------------------------------------------------------------------ sesión
async function iniciar() {
  if (DEMO) { yo = {rol: 'docente', nombre: 'Demostración'}; return mostrarApp(); }
  if (!CFG.supabaseUrl || !CFG.supabaseClave) {
    $('entrar').classList.remove('oculto');
    $('e-entrar').textContent = 'Falta config.js (viaviva nube preparar). Mientras tanto, vea la DEMOSTRACIÓN.';
    $('e-entrar').classList.remove('oculto');
    return;
  }
  sb = createClient(CFG.supabaseUrl, CFG.supabaseClave);
  const {data} = await sb.auth.getSession();
  if (!data.session) return $('entrar').classList.remove('oculto');
  const {data: perfil} = await sb.from('perfiles').select('rol,nombre').eq('usuario_id', data.session.user.id).maybeSingle();
  if (!perfil) {
    $('entrar').classList.remove('oculto');
    $('e-entrar').textContent = 'Su cuenta no tiene rol asignado: pídaselo al equipo.'; $('e-entrar').classList.remove('oculto');
    return;
  }
  yo = {...perfil, correo: data.session.user.email};
  mostrarApp();
}
$('f-entrar').onsubmit = async (ev) => {
  ev.preventDefault();
  if (!sb) return;
  const {error} = await sb.auth.signInWithPassword({email: $('correo').value, password: $('clave').value});
  if (error) { $('e-entrar').textContent = 'No se pudo entrar: ' + error.message; $('e-entrar').classList.remove('oculto'); return; }
  location.reload();
};

function mostrarApp() {
  $('entrar').classList.add('oculto'); $('app').classList.remove('oculto');
  $('cuenta').innerHTML = esc(yo.nombre || yo.correo || '') + ' <span class="rol">' + esc({editor: 'Editor',
    alcaldia: 'Alcaldía', docente: 'Docente'}[yo.rol]) + '</span>' + (DEMO ? '' : ' <a href="#" id="b-salir">Salir</a>');
  if ($('b-salir')) $('b-salir').onclick = async (e) => { e.preventDefault(); await sb.auth.signOut(); location.reload(); };
  if (yo.rol === 'editor') $('b-importar').classList.remove('oculto');
  if (DEMO) aviso('DEMOSTRACIÓN: baches y riesgo INVENTADOS en el navegador para mostrar el diseño. No son datos de Tunja.');
  crearMapa();
}

function aviso(t) { $('aviso').textContent = t; $('aviso').classList.toggle('oculto', !t); }

// ------------------------------------------------------------------ datos
async function cargarDatos() {
  if (DEMO) return datosDemo();
  const [h, r] = await Promise.all([sb.from('huecos_publicos').select('*').order('ultima_ts', {ascending: false}).limit(5000),
                                    sb.from('riesgo_ultimo').select('id_tramo,probabilidad,rango,modelo,version_modelo,fecha_calculo')]);
  if (h.error || r.error) { aviso('Error al leer: ' + (h.error || r.error).message); return; }
  huecos = h.data; riesgo = r.data;
  corrida = riesgo[0] ? {modelo: riesgo[0].modelo, version: riesgo[0].version_modelo, fecha: riesgo[0].fecha_calculo} : null;
  if (corrida && /DEMO|SINTETICO/i.test(corrida.version)) aviso('La corrida de riesgo es DEMO/SINTÉTICA: no es un resultado.');
}

function datosDemo() {
  let s = 7; const azar = () => (s = (s * 16807) % 2147483647) / 2147483647;
  const f = tramos.features;
  riesgo = f.map((t) => ({id_tramo: t.id, probabilidad: Math.min(0.97, azar() ** 4 + (t.properties.t === 'primary' ? 0.2 : 0))}));
  corrida = {modelo: 'bosque', version: 'DEMO', fecha: new Date().toISOString()};
  const clases = ['hueco', 'hueco', 'hueco', 'impacto_fuerte', 'hueco'], sev = ['baja', 'media', 'alta'];
  huecos = Array.from({length: 140}, (_, i) => {
    const t = f[Math.floor(azar() * f.length)], c = t.geometry.coordinates[0];
    const dias = Math.floor(azar() * 60), est = ESTADOS[Math.min(3, Math.floor(azar() ** 1.6 * 3.4))];
    return {id_origen: 'demo|' + i, id_local: i + 1, lat: c[1], lon: c[0], clase: clases[i % 5], severidad: sev[Math.floor(azar() * 3)],
      n_detecciones: 1 + Math.floor(azar() * 5), estado: est, id_tramo: t.id,
      primera_ts: new Date(Date.now() - dias * 864e5).toISOString(), ultima_ts: new Date(Date.now() - dias * 4e7).toISOString(),
      ts_estado: est === 'reparado' ? new Date(Date.now() - azar() * 20 * 864e5).toISOString() : null};
  });
}

function filtrados() {
  const e = $('f-estado').value, c = $('f-clase').value, sv = $('f-sev').value;
  const d = $('f-desde').value ? new Date($('f-desde').value) : null, h = $('f-hasta').value ? new Date($('f-hasta').value + 'T23:59') : null;
  return huecos.filter((x) => (!e || (e === 'abiertos' ? ['detectado', 'verificado'].includes(x.estado) : x.estado === e))
    && (!c || x.clase === c) && (!sv || x.severidad === sv)
    && (!d || new Date(x.ultima_ts) >= d) && (!h || new Date(x.primera_ts) <= h));
}

// ------------------------------------------------------------------ mapa
function estiloMapa() {
  return 'https://tiles.openfreemap.org/styles/' + (document.documentElement.dataset.theme === 'dark' ? 'dark' : 'positron');
}

async function crearMapa() {
  tramos = await (await fetch('datos/tramos.geojson')).json().catch(() => ({type: 'FeatureCollection', features: []}));
  if (!tramos.features.length) aviso('Falta datos/tramos.geojson (viaviva nube preparar).');
  await cargarDatos();
  const clases = [...new Set(huecos.map((x) => x.clase))].sort();
  $('f-clase').innerHTML = '<option value="">Todas las clases</option>' + clases.map((c) => `<option>${esc(c)}</option>`).join('');
  mapa = new maplibregl.Map({container: 'mapa', style: estiloMapa(), center: [-73.3605, 5.5440], zoom: 13,
                             attributionControl: {compact: true}, canvasContextAttributes: {preserveDrawingBuffer: true}});
  mapa.addControl(new maplibregl.NavigationControl({showCompass: false}), 'top-right');
  mapa.on('style.load', capas);
  for (const id of ['f-estado', 'f-clase', 'f-sev', 'f-desde', 'f-hasta']) $(id).onchange = pintar;
  $('c-huecos').onchange = () => visibles();
  $('c-riesgo').onchange = () => visibles();
  leyenda(); pintar();
  setInterval(async () => { await cargarDatos(); pintar(); }, KIOSCO ? 60000 : 120000);
}

function capas() {
  const p = new Map(riesgo.map((r) => [r.id_tramo, r.probabilidad]));
  const conRiesgo = {...tramos, features: tramos.features.filter((f) => p.has(f.id)).map((f) => ({...f,
    properties: {...f.properties, p: p.get(f.id)}}))};
  mapa.addSource('tramos', {type: 'geojson', data: conRiesgo});
  mapa.addLayer({id: 'riesgo', type: 'line', source: 'tramos', paint: {
    'line-color': ['step', ['get', 'p'], css('--r1'), CORTES[0], css('--r2'), CORTES[1], css('--r3'), CORTES[2], css('--r4'), CORTES[3], css('--r5')],
    'line-width': ['interpolate', ['linear'], ['zoom'], 12, ['case', ['>=', ['get', 'p'], 0.6], 2.5, 1], 17, ['case', ['>=', ['get', 'p'], 0.6], 7, 3]],
    'line-opacity': 0.9}});
  mapa.addSource('huecos', {type: 'geojson', data: geojsonHuecos()});
  mapa.addLayer({id: 'huecos', type: 'circle', source: 'huecos', paint: {
    'circle-color': ['match', ['get', 'estado'], 'detectado', css('--est-detectado'), 'verificado', css('--est-verificado'),
      'reparado', css('--est-reparado'), css('--est-descartado')],
    'circle-radius': ['match', ['get', 'severidad'], 'alta', 8, 'media', 6, 4.5],
    'circle-stroke-color': '#fff', 'circle-stroke-width': 1.5}});
  mapa.on('click', 'huecos', (e) => detalle(huecos.find((h) => h.id_origen === e.features[0].properties.id)));
  mapa.on('click', 'riesgo', (e) => {
    const f = e.features[0].properties;
    new maplibregl.Popup().setLngLat(e.lngLat).setHTML(`<b>${esc(f.n || 'Tramo ' + f.id)}</b><br>Riesgo ${Math.round(f.p * 100)} % · `
      + `${esc(f.t || '')} · ${esc(f.b || '')}`).addTo(mapa);
  });
  for (const l of ['huecos', 'riesgo']) {
    mapa.on('mouseenter', l, () => { mapa.getCanvas().style.cursor = 'pointer'; });
    mapa.on('mouseleave', l, () => { mapa.getCanvas().style.cursor = ''; });
  }
  visibles();
}

function geojsonHuecos() {
  return {type: 'FeatureCollection', features: filtrados().map((h) => ({type: 'Feature',
    properties: {id: h.id_origen, estado: h.estado, severidad: h.severidad || 'baja'},
    geometry: {type: 'Point', coordinates: [h.lon, h.lat]}}))};
}

function visibles() {
  if (!mapa.getLayer('huecos')) return;
  mapa.setLayoutProperty('huecos', 'visibility', $('c-huecos').checked ? 'visible' : 'none');
  mapa.setLayoutProperty('riesgo', 'visibility', $('c-riesgo').checked ? 'visible' : 'none');
}

function leyenda() {
  $('leyenda').innerHTML = '<b>Riesgo:</b>' + ['< 20 %', '20–40', '40–60', '60–80', '≥ 80 %'].map((t, i) =>
    `<span><i style="background:var(--r${i + 1})"></i>${t}</span>`).join('') + '<b>Baches:</b>' + ESTADOS.map((e) =>
    `<span><i class="b" style="background:var(--est-${e})"></i>${NOMBRE[e]}</span>`).join('') + '<span>tamaño = severidad</span>';
}

// ------------------------------------------------------------------ indicadores, tabla y gráficos
function pintar() {
  if (mapa?.getSource('huecos')) mapa.getSource('huecos').setData(geojsonHuecos());
  const ab = huecos.filter((h) => ['detectado', 'verificado'].includes(h.estado));
  const hace30 = Date.now() - 30 * 864e5;
  $('k-abiertos').textContent = ab.length;
  $('k-abiertos-s').textContent = ab.filter((h) => h.severidad === 'alta').length + ' de severidad alta';
  $('k-verif').textContent = huecos.filter((h) => h.estado === 'verificado').length;
  $('k-rep').textContent = huecos.filter((h) => h.estado === 'reparado' && new Date(h.ts_estado) >= hace30).length;
  $('k-rep-s').textContent = huecos.filter((h) => h.estado === 'reparado').length + ' en total';
  $('k-crit').textContent = riesgo.filter((r) => r.probabilidad >= 0.6).length;
  $('corrida').textContent = corrida ? `· ${corrida.modelo} ${corrida.version}` : '· sin corridas';
  $('t-vivo').textContent = 'actualizado ' + new Date().toLocaleTimeString('es-CO', {hour: '2-digit', minute: '2-digit'});
  const nombres = new Map(tramos.features.map((f) => [f.id, f.properties]));
  const abiertosPorTramo = new Map();
  for (const h of ab) abiertosPorTramo.set(h.id_tramo, (abiertosPorTramo.get(h.id_tramo) || 0) + 1);
  const top = [...riesgo].sort((a, b) => b.probabilidad - a.probabilidad).slice(0, 10);
  $('top').innerHTML = top.map((r, i) => `<tr data-t="${r.id_tramo}"><td>${i + 1}</td><td>${esc(nombres.get(r.id_tramo)?.n || 'tramo ' + r.id_tramo)}`
    + `<br><small class="sub">${esc(nombres.get(r.id_tramo)?.b || '')}</small></td><td class="num">${Math.round(r.probabilidad * 100)} %</td>`
    + `<td class="num">${abiertosPorTramo.get(r.id_tramo) || 0}</td></tr>`).join('') || '<tr><td colspan="4" class="sub">Sin datos de riesgo</td></tr>';
  for (const tr of $('top').querySelectorAll('tr[data-t]')) tr.onclick = () => {
    const f = tramos.features.find((x) => x.id === +tr.dataset.t);
    if (f) mapa.fitBounds(f.geometry.coordinates.reduce((b, c) => b.extend(c), new maplibregl.LngLatBounds(f.geometry.coordinates[0], f.geometry.coordinates[0])), {padding: 80, maxZoom: 17});
  };
  graficar();
}

function graficar() {
  const lista = filtrados();
  const porClase = {};
  for (const h of lista) porClase[h.clase] = (porClase[h.clase] || 0) + 1;
  const semanas = {};
  for (const h of huecos) {
    const d = new Date(h.primera_ts); d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    const k = d.toISOString().slice(0, 10); semanas[k] = (semanas[k] || 0) + 1;
  }
  const claves = Object.keys(semanas).sort().slice(-12);
  const color = css('--pico-primary') || '#1f6feb', texto = css('--pico-muted-color');
  Chart.defaults.color = texto; Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  const datos = {
    'g-clase': {type: 'bar', data: {labels: Object.keys(porClase), datasets: [{data: Object.values(porClase), backgroundColor: color, borderRadius: 6}]}},
    'g-semana': {type: 'line', data: {labels: claves.map((k) => k.slice(5)), datasets: [{data: claves.map((k) => semanas[k]),
      borderColor: color, backgroundColor: color + '33', fill: true, tension: 0.3, pointRadius: 3}]}},
  };
  for (const [id, cfg] of Object.entries(datos)) {
    if (graficos[id]) { graficos[id].data = cfg.data; graficos[id].update('none'); continue; }
    graficos[id] = new Chart($(id), {...cfg, options: {plugins: {legend: {display: false}}, animation: {duration: matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 400},
      scales: {y: {beginAtZero: true, ticks: {precision: 0}}, x: {grid: {display: false}}}}});
  }
}

// ------------------------------------------------------------------ detalle y cambio de estado (editores)
function detalle(h) {
  if (!h) return;
  $('h-titulo').innerHTML = `Bache #${h.id_local} <span class="estado"><i style="background:var(--est-${h.estado})"></i>${NOMBRE[h.estado]}</span>`;
  const editor = yo.rol === 'editor' && !DEMO;
  $('h-cuerpo').innerHTML = `<p>${esc(h.clase === 'impacto_fuerte' ? 'Impacto sin clasificar' : h.clase)} · severidad ${esc(h.severidad || '—')} · `
    + `${h.n_detecciones} detección(es)<br><small class="sub">Primera ${fecha(h.primera_ts)} · última ${fecha(h.ultima_ts)} · `
    + `${h.lat.toFixed(5)}, ${h.lon.toFixed(5)}</small></p>`
    + (editor ? '<div class="botones-estado">' + ESTADOS.map((e) => `<button class="${e === h.estado ? '' : 'secondary outline'}" data-e="${e}">${NOMBRE[e]}</button>`).join('')
      + '</div><input id="nota" placeholder="Nota (opcional, ≤ 300)" maxlength="300"><p class="sub">El cambio queda pendiente hasta que la Pi sincronice (la base de la Pi manda).</p>'
      : '<p class="sub">Solo lectura.</p>');
  for (const b of $('h-cuerpo').querySelectorAll('[data-e]')) b.onclick = async () => {
    const {error} = await sb.from('cambios_remotos').insert({id_origen: h.id_origen, instancia: h.instancia, id_local: h.id_local,
      estado: b.dataset.e, nota: $('nota').value || null});
    aviso(error ? 'No se guardó: ' + error.message : `Bache #${h.id_local}: «${NOMBRE[b.dataset.e]}» enviado; se verá al sincronizar la Pi.`);
    $('d-hueco').close();
  };
  $('d-hueco').showModal();
}

// ------------------------------------------------------------------ exportar
function descargar(nombre, contenido, tipo) {
  const a = Object.assign(document.createElement('a'), {href: URL.createObjectURL(new Blob([contenido], {type: tipo})), download: nombre});
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
const COLS = ['id_local', 'estado', 'clase', 'severidad', 'n_detecciones', 'lat', 'lon', 'id_tramo', 'primera_ts', 'ultima_ts', 'ts_estado'];
const sello = () => new Date().toISOString().slice(0, 16).replace(/[:T]/g, '');
$('x-csv').onclick = (e) => {
  e.preventDefault();
  const filas = [COLS.join(','), ...filtrados().map((h) => COLS.map((c) => JSON.stringify(h[c] ?? '')).join(','))];
  descargar(`viaviva_baches_${sello()}.csv`, '﻿' + filas.join('\n'), 'text/csv;charset=utf-8');
};
$('x-xlsx').onclick = async (e) => {
  e.preventDefault();
  const XLSX = await import('https://cdn.sheetjs.com/xlsx-0.20.3/package/xlsx.mjs');
  const libro = XLSX.utils.book_new();
  const nombres = new Map(tramos.features.map((f) => [f.id, f.properties]));
  XLSX.utils.book_append_sheet(libro, XLSX.utils.json_to_sheet(filtrados().map((h) => Object.fromEntries(COLS.map((c) => [c, h[c]])))), 'Baches');
  XLSX.utils.book_append_sheet(libro, XLSX.utils.json_to_sheet([...riesgo].sort((a, b) => b.probabilidad - a.probabilidad).map((r) =>
    ({id_tramo: r.id_tramo, calle: nombres.get(r.id_tramo)?.n || '', barrio: nombres.get(r.id_tramo)?.b || '', probabilidad: r.probabilidad}))), 'Riesgo por tramo');
  XLSX.utils.book_append_sheet(libro, XLSX.utils.aoa_to_sheet([['VÍA VIVA', DEMO ? 'DEMOSTRACIÓN: datos inventados' : ''],
    ['Generado', new Date().toLocaleString('es-CO')], ['Corrida de riesgo', corrida ? `${corrida.modelo} ${corrida.version}` : '—'],
    ...ESTADOS.map((s) => [NOMBRE[s], huecos.filter((h) => h.estado === s).length])]), 'Resumen');
  XLSX.writeFile(libro, `viaviva_${sello()}.xlsx`);
};
$('x-pdf').onclick = (e) => { e.preventDefault(); document.querySelector('.menu-exportar').open = false; setTimeout(() => print(), 200); };

// ------------------------------------------------------------------ importar reparaciones (editores)
let cambiosCSV = [];
$('b-importar').onclick = () => { $('vista').innerHTML = ''; $('b-enviar').disabled = true; $('d-importar').showModal(); };
$('archivo').onchange = async () => {
  const texto = (await $('archivo').files[0].text()).replace(/^﻿/, '');
  const sep = (texto.split('\n')[0].match(/;/g) || []).length > (texto.split('\n')[0].match(/,/g) || []).length ? ';' : ',';
  const filas = texto.split(/\r?\n/).filter((l) => l.trim()).map((l) => l.split(sep).map((x) => x.trim().replace(/^"|"$/g, '')));
  const cab = filas.shift().map((c) => c.toLowerCase());
  const i = (n) => cab.indexOf(n);
  const errores = [], vistos = new Set(), hoy = new Date();
  cambiosCSV = [];
  if (i('id_hueco') < 0) errores.push([1, 'falta la columna id_hueco']);
  filas.forEach((f, k) => {
    const n = k + 2, id = parseInt(f[i('id_hueco')], 10), est = (f[i('estado')] || 'reparado').toLowerCase();
    const h = huecos.find((x) => x.id_local === id);
    if (!h) return errores.push([n, `el bache ${f[i('id_hueco')]} no existe`]);
    if (vistos.has(id)) return errores.push([n, `bache ${id} repetido`]);
    vistos.add(id);
    if (!ESTADOS.includes(est)) return errores.push([n, `estado «${est}» no válido`]);
    const fe = f[i('fecha')] ? new Date(f[i('fecha')]) : null;
    if (est === 'reparado' && !fe) return errores.push([n, 'falta la fecha de la reparación']);
    if (fe && (isNaN(fe) || fe > hoy)) return errores.push([n, `fecha «${f[i('fecha')]}» inválida o futura`]);
    cambiosCSV.push({id_origen: h.id_origen, instancia: h.instancia, id_local: id, estado: est, origen: 'csv',
                     nota: [f[i('fecha')] ? 'reparado el ' + f[i('fecha')] : '', f[i('nota')] || ''].filter(Boolean).join(' · ').slice(0, 300) || null});
  });
  $('vista').innerHTML = `<p>${filas.length} filas · ${cambiosCSV.length} válidas · <b>${errores.length} errores</b></p>`
    + (errores.length ? '<table class="tabla">' + errores.map(([n, m]) => `<tr><td>Fila ${n}</td><td>${esc(m)}</td></tr>`).join('') + '</table>'
      : '<table class="tabla">' + cambiosCSV.map((c) => `<tr><td>#${c.id_local}</td><td>${NOMBRE[c.estado]}</td><td>${esc(c.nota || '')}</td></tr>`).join('') + '</table>');
  $('b-enviar').disabled = errores.length > 0 || !cambiosCSV.length;
};
$('b-enviar').onclick = async () => {
  const {error} = await sb.from('cambios_remotos').insert(cambiosCSV);
  aviso(error ? 'No se envió: ' + error.message : `${cambiosCSV.length} cambios enviados; se aplican al sincronizar la Pi.`);
  $('d-importar').close();
};

iniciar();
