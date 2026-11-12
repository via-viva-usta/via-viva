// VÍA VIVA · tablero en línea (estático, Netlify). Lee de Supabase con la clave pública + sesión (RLS por rol).
// ?demo=1 → datos INVENTADOS en el navegador para ver el diseño sin cuenta (con aviso).  ?kiosco=1 → pantalla fija.
// ?demo=1&rol=editor → muestra también los controles de edición (en DEMO no se envía nada).
// Módulos: reglas.js (vocabulario y fórmulas, sin dependencias) · carga.js (Supabase, DEMO, preparación) · mapa.js.
// Recorrido de la pantalla: cifras (también son atajos) → filtros (lo secundario, plegado) → mapa (modo Huecos o
// Riesgo) + panel (Para atender · Riesgo · Tendencia). El detalle de un hueco se abre en el panel: el mapa sigue a la
// vista. Para no saturar: los datos entran por partes, la lista muestra pocos y se pide más, la leyenda va plegada.
// Desde la portada (index.html) se puede llegar directo a una pestaña: tablero.html#riesgo · #tendencia · #atender.
import Chart from 'https://cdn.jsdelivr.net/npm/chart.js@4.6.1/auto/+esm';
import {createClient} from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.119.0/+esm';
import {cambiosPendientes, cargarSupabase, cargarTramos, datosDemo, preparar} from './carga.js';
import {Mapa, leyendaHTML, leyendaResumen} from './mapa.js';
import * as R from './reglas.js';

const $ = (id) => document.getElementById(id);
const P = new URLSearchParams(location.search);
const DEMO = P.has('demo'), KIOSCO = P.has('kiosco');
const CFG = window.VIAVIVA || {};
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const movil = () => matchMedia('(max-width: 960px)').matches;
const plural = (n, uno, varios) => `${n.toLocaleString('es-CO')} ${n === 1 ? uno : varios}`;
const DIA = 864e5, QUIETO = matchMedia('(prefers-reduced-motion: reduce)').matches;
const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

const ui = {filtro: {vista: 'abiertos', sev: '', clase: '', periodo: 'todo', desde: '', hasta: ''}, modo: 'huecos',
  seleccion: null, limite: null};      // limite = filas de la lista («Mostrar más»); null = las de siempre
let sb = null, yo = null, mapa = null, tramos = null, grafico = null, grupos = new Map();
let D = preparar([], [], {features: []});
let vista = {base: [], visibles: [], rango: null};
let animarDesde = 0;           // filas de la lista que entran con animación (0 = todas; Infinity = ninguna)

// ------------------------------------------------------------------ tema, pantalla fija, diálogos y avisos
$('b-tema').onclick = () => {
  const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem('vv_tema', t); } catch (e) { /* sin almacenamiento: dura hasta recargar */ }
  mapa?.cambiarTema();
  grafico?.destroy(); grafico = null;
  if (mapa) tendencia(vista.base);
};
$('b-kiosco').onclick = () => { const u = new URL(location); u.searchParams.set('kiosco', '1'); location = u; };
if (KIOSCO) {
  document.body.classList.add('kiosco');
  document.addEventListener('click', () => document.documentElement.requestFullscreen?.().catch(() => {}), {once: true});
  navigator.wakeLock?.request('screen').catch(() => {});
  addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !document.fullscreenElement) { const u = new URL(location); u.searchParams.delete('kiosco'); location = u; }
  });
}
for (const d of document.querySelectorAll('dialog')) d.addEventListener('click', (e) => { if (e.target === d) d.close(); });
for (const b of document.querySelectorAll('[data-cerrar]')) b.onclick = () => b.closest('dialog').close();
$('b-ayuda').onclick = () => $('d-ayuda').showModal();
$('b-ayuda-pie').onclick = (e) => { e.preventDefault(); $('d-ayuda').showModal(); };

const avisos = new Map();
function ponerAviso(clave, texto) {
  texto ? avisos.set(clave, texto) : avisos.delete(clave);
  $('aviso').innerHTML = [...avisos.values()].map(esc).join('<br>');
  $('aviso').classList.toggle('oculto', !avisos.size);
}
let relojToast;
function toast(texto) {
  $('toast').textContent = texto; $('toast').classList.remove('oculto');
  clearTimeout(relojToast); relojToast = setTimeout(() => $('toast').classList.add('oculto'), 5000);
}
const vacio = (titulo, texto) => `<li class="vacio"><b>${esc(titulo)}</b>${texto}</li>`;

// ------------------------------------------------------------------ sesión
async function iniciar() {
  window.VV_ARRANCO = true;                  // las librerías cargaron: vigia.js ya no avisa
  if (DEMO) {
    const rol = ['editor', 'alcaldia', 'docente'].includes(P.get('rol')) ? P.get('rol') : 'docente';
    yo = {rol, nombre: 'Demostración'};
    return mostrarApp();
  }
  if (!CFG.supabaseUrl || !CFG.supabaseClave) {
    $('entrar').classList.remove('oculto');
    $('e-entrar').textContent = 'Falta config.js (viaviva nube preparar). Mientras tanto, vea la DEMOSTRACIÓN.';
    $('e-entrar').classList.remove('oculto');
    $('t-frescura').textContent = 'Sin conexión configurada';
    return;
  }
  sb = createClient(CFG.supabaseUrl, CFG.supabaseClave);
  const {data} = await sb.auth.getSession();
  if (!data.session) { $('t-frescura').textContent = 'Inicie sesión'; return $('entrar').classList.remove('oculto'); }
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

async function mostrarApp() {
  $('entrar').classList.add('oculto'); $('app').classList.remove('oculto'); $('b-kiosco').classList.remove('oculto');
  $('cuenta').innerHTML = esc(yo.nombre || yo.correo || '') + ' <span class="rol">' + esc({editor: 'Editor',
    alcaldia: 'Alcaldía', docente: 'Docente'}[yo.rol]) + '</span>' + (DEMO ? '' : ' <a href="#" id="b-salir">Salir</a>');
  if ($('b-salir')) $('b-salir').onclick = async (e) => { e.preventDefault(); await sb.auth.signOut(); location.reload(); };
  if (yo.rol === 'editor') $('b-importar').classList.remove('oculto');
  if (DEMO) $('franja-demo').classList.remove('oculto');      // franja amarilla: imposible de no ver, sin tapar
  tramos = await cargarTramos();
  if (!tramos.features.length) ponerAviso('tramos', 'Falta datos/tramos.geojson (viaviva nube preparar): no se pueden mostrar calles ni riesgo.');
  else if (tramos.demo && !DEMO) {
    ponerAviso('tramos', 'El archivo de calles es de DEMOSTRACIÓN (herramientas/tramos_demo.py): sus números de tramo no '
      + 'coinciden con la base y el riesgo no se puede ubicar. Publique el de «viaviva nube preparar».');
  }
  mapa = new Mapa($('mapa'), {alTocarHueco: (id) => abrirDetalle(id), htmlTramo, htmlHuecoCorto});
  conectarControles();
  sincronizarControles();
  document.body.classList.add('cargando');
  await recargar();
  entrada();
  irAlDestino();
  setInterval(recargar, KIOSCO ? 60000 : 120000);
}

// ------------------------------------------------------------------ datos y filtros
async function recargar() {
  try {
    const crudo = DEMO ? datosDemo(tramos) : await cargarSupabase(sb);
    D = preparar(crudo.huecos, crudo.riesgo, tramos);
    ponerAviso('error', '');
  } catch (e) {
    ponerAviso('error', 'No se pudieron leer los datos: ' + (e.message || e) + '. Se muestran los últimos que se cargaron.');
  }
  ponerAviso('corrida', D.corrida?.demo && !DEMO ? 'La corrida de riesgo es DEMO/SINTÉTICA: sirve para probar el tablero, no es un resultado.' : '');
  mapa.ponerTramos(D.tramosRiesgo);
  opcionesTipo();
  if (ui.modo === 'riesgo' && !D.riesgo.length) ponerModo('huecos');
  pintar();
}

function opcionesTipo() {
  const clases = [...new Set(D.huecos.map((h) => h.clase))].sort();
  if (!clases.includes(ui.filtro.clase)) ui.filtro.clase = '';
  $('f-clase').innerHTML = '<option value="">Todos</option>'
    + clases.map((c) => `<option value="${esc(c)}">${esc(R.nombreClase(c))}</option>`).join('');
  $('f-clase').value = ui.filtro.clase;
}

/** [desde, hasta] en milisegundos, o null si es «Todo». Las fechas elegidas se leen en hora de Tunja. */
function rango() {
  const f = ui.filtro;
  if (f.periodo === 'todo') return null;
  if (f.periodo === 'rango') {
    if (!f.desde && !f.hasta) return null;
    const a = f.desde ? R.diaLocal(f.desde).getTime() : -Infinity, b = f.hasta ? R.diaLocal(f.hasta, true).getTime() : Infinity;
    return a <= b ? [a, b] : [R.diaLocal(f.hasta).getTime(), R.diaLocal(f.desde, true).getTime()];
  }
  return [Date.now() - Number(f.periodo) * DIA, Date.now()];
}

/** base = filtros de severidad, tipo y periodo (cifras y tendencia); visibles = base + Abiertos/Reparados/Todos. */
function filtrar() {
  const f = ui.filtro, r = rango();
  const base = D.huecos.filter((h) => (!f.sev || h.severidad === f.sev) && (!f.clase || h.clase === f.clase)
    && (!r || (h.inicio <= r[1] && h.fin >= r[0])));        // un hueco cuenta si tuvo actividad dentro del periodo
  const visibles = base.filter((h) => (f.vista === 'abiertos' ? h.abierto : f.vista === 'reparados' ? h.estado === 'reparado' : true));
  return {base, visibles, rango: r};
}
const orden = (a, b) => (b.abierto - a.abierto)
  || (a.abierto ? b.prioridad - a.prioridad || b.nivelSev - a.nivelSev || b.fin - a.fin : b.fin - a.fin);

function pintar() {
  vista = filtrar();
  cifras(vista); contexto(vista); lista(vista.visibles); tramosTop(); tendencia(vista.base); frescura();
  mapa.ponerHuecos(vista.visibles);
  ponerLeyenda();
  const bRiesgo = $('f-modo').querySelector('[data-m="riesgo"]');
  bRiesgo.disabled = !D.riesgo.length;
  bRiesgo.title = D.riesgo.length ? '' : 'Aún no hay corridas del modelo de riesgo';
  if (ui.seleccion) {
    const h = D.huecos.find((x) => x.id_origen === ui.seleccion);
    if (!h) cerrarDetalle();
    else if (!$('detalle').contains(document.activeElement)) mostrarDetalle(h);   // no borra una nota a medio escribir
  }
}

// ------------------------------------------------------------------ cifras, contexto y frescura
function poner(id, n, sub) {
  const b = $(id).querySelector('b');
  b.dataset.valor = typeof n === 'number' ? n : '';
  b.textContent = typeof n === 'number' ? n.toLocaleString('es-CO') : n;
  $(id).querySelector('small').textContent = sub;
}
function cifras({base, rango: r}) {
  const ab = base.filter((h) => h.abierto), det = ab.filter((h) => h.estado === 'detectado').length;
  const alta = ab.filter((h) => h.severidad === 'alta').length;
  const enRango = (ts) => !r || (R.ms(ts) >= r[0] && R.ms(ts) <= r[1]);
  const rep = base.filter((h) => h.estado === 'reparado' && enRango(h.ts_estado));
  const conDias = rep.filter((h) => h.diasReparacion != null);
  const prom = conDias.length ? conDias.reduce((s, h) => s + h.diasReparacion, 0) / conDias.length : null;
  poner('k-abiertos', ab.length, ab.length ? `${plural(det, 'detectado', 'detectados')} · ${plural(ab.length - det, 'verificado', 'verificados')}` : 'ninguno con estos filtros');
  poner('k-alta', alta, ab.length ? `${Math.round(100 * alta / ab.length)} % de los abiertos` : '—');
  $('k-reparados').querySelector('.et').textContent = r ? 'Reparados en el periodo' : 'Reparados';
  poner('k-reparados', rep.length, prom != null ? `tardaron ${R.textoDias(prom)} en promedio` : 'sin reparaciones registradas');
  const altos = D.riesgo.filter((x) => x.probabilidad >= R.RIESGO_ALTO).length;
  poner('k-riesgo', D.riesgo.length ? altos : '—', D.riesgo.length
    ? `de ${D.riesgo.length.toLocaleString('es-CO')} tramos` : 'aún no hay corrida del modelo');
  const f = ui.filtro;
  $('k-abiertos').setAttribute('aria-pressed', f.vista === 'abiertos' && !f.sev);
  $('k-alta').setAttribute('aria-pressed', f.vista === 'abiertos' && f.sev === 'alta');
  $('k-reparados').setAttribute('aria-pressed', f.vista === 'reparados');
  $('k-riesgo').setAttribute('aria-pressed', ui.modo === 'riesgo');
}

function textoPeriodo(r) {
  const f = ui.filtro;
  if (!r) return 'todo el periodo';
  if (f.periodo !== 'rango') return `últimos ${f.periodo} días`;
  return [Number.isFinite(r[0]) ? 'desde el ' + R.fechaDia(r[0]) : '', Number.isFinite(r[1]) ? 'hasta el ' + R.fechaDia(r[1]) : ''].filter(Boolean).join(' ');
}
function contexto({visibles, rango: r}) {
  const f = ui.filtro;
  const que = {abiertos: ['hueco abierto', 'huecos abiertos'], reparados: ['hueco reparado', 'huecos reparados'],
    todos: ['hueco (todos los estados)', 'huecos (todos los estados)']}[f.vista];
  const activos = [];
  if (f.sev) activos.push(['sev', 'Severidad ' + R.SEVERIDAD[f.sev].toLowerCase()]);
  if (f.clase) activos.push(['clase', R.nombreClase(f.clase)]);
  if (r) activos.push(['periodo', textoPeriodo(r)[0].toUpperCase() + textoPeriodo(r).slice(1)]);
  $('contexto').innerHTML = `<span>En el mapa: <b>${plural(visibles.length, ...que)}</b>${activos.length ? '' : ' · todo el periodo'}.</span>`
    + activos.map(([k, t]) => `<button type="button" class="filtro-activo" data-quitar="${k}" aria-label="Quitar el filtro ${esc(t)}">`
      + `${esc(t)} <span aria-hidden="true">✕</span></button>`).join('');
}

function frescura() {
  const el = $('frescura'), t = $('t-frescura');
  el.classList.remove('al-dia', 'viejo');
  if (DEMO) { t.textContent = 'Datos de demostración'; return; }
  if (!D.ultimoDato) { t.textContent = 'Sin datos sincronizados todavía'; el.classList.add('viejo'); return; }
  const reciente = Date.now() - D.ultimoDato <= 2 * DIA;
  el.classList.add(reciente ? 'al-dia' : 'viejo');
  t.textContent = reciente ? `Último dato: ${R.fechaHora(D.ultimoDato)}` : `Último dato: ${R.fechaDia(D.ultimoDato)} (${R.hace(D.ultimoDato)})`;
}

// ------------------------------------------------------------------ lista «Para atender» y detalle
function chipSev(h) {
  if (!h.severidad) return '<span class="chip">severidad sin dato</span>';
  const n = {alta: 3, media: 2, baja: 1}[h.severidad];
  return `<span class="chip${n === 3 ? ' fuerte' : ''}"><span class="sev n${n}" aria-hidden="true"><i></i><i></i><i></i></span>`
    + `severidad ${R.SEVERIDAD[h.severidad].toLowerCase()}</span>`;
}
function filaHueco(h, i) {
  const n = {alta: 3, media: 2, baja: 1}[h.severidad];
  const partes = [n ? `<span class="sev n${n}" aria-hidden="true"><i></i><i></i><i></i></span>Severidad ${R.SEVERIDAD[h.severidad].toLowerCase()}`
    : 'Severidad sin dato'];
  if (h.abierto && h.pesoVia > 1) partes.push(esc(h.via));
  if (h.abierto && h.enTramo > 1) partes.push(`<span class="fuerte">${h.enTramo} en el tramo</span>`);
  if (h.diasReparacion != null) partes.push(`reparado en ${R.textoDias(h.diasReparacion)}`);
  if (h.estado === 'descartado') partes.push('descartado');
  if (h.barrio) partes.push(esc(h.barrio));
  const marca = h.abierto ? `<span class="num lleno" style="--c:var(--vv-${h.estado})" aria-hidden="true">${i + 1}</span>`
    : `<span class="num" style="--c:var(--vv-${h.estado})" aria-hidden="true">${h.estado === 'reparado' ? '✓' : '×'}</span>`;
  // a la derecha, el tiempo con su significado (en el celular no hay «title» que lo explique)
  const der = h.abierto ? `<b>${R.textoDias(h.diasAbierto)}</b>abierto`
    : `<b>${esc(R.fechaDia(h.ts_estado || h.ultima_ts).replace(/ de \d{4}$/, ''))}</b>${h.estado}`;
  const entra = i >= animarDesde ? ` class="entra" style="--i:${Math.min(i - animarDesde, 12)}"` : '';
  return `<li${entra}><button type="button" class="fila" data-id="${esc(h.id_origen)}" aria-current="${ui.seleccion === h.id_origen}">`
    + `${marca}<span><span class="fila-titulo"><span class="oculto-visual">${R.ESTADO[h.estado].nombre}: </span>${esc(h.lugar)}</span>`
    + `<span class="fila-sub">${partes.join(' · ')}</span></span><span class="fila-der">${der}</span></button></li>`;
}
function lista(visibles) {
  const v = ui.filtro.vista;
  $('t-atender-txt').textContent = {abiertos: 'Para atender', reparados: 'Reparados', todos: 'Huecos'}[v];
  $('n-atender').textContent = visibles.length.toLocaleString('es-CO');
  $('ayuda-lista').textContent = {
    abiertos: 'Los más urgentes primero. Toque uno para verlo en el mapa.',
    reparados: 'Las reparaciones más recientes primero.',
    todos: 'Primero los abiertos (por prioridad) y después los cerrados, del más reciente al más antiguo.'}[v];
  if (!D.huecos.length) {
    $('lista').innerHTML = vacio('Todavía no hay huecos sincronizados',
      'Aparecen aquí cuando la Raspberry Pi o el PC de captura se conectan a internet.');
    $('lista-pie').textContent = '';
    return;
  }
  const ordenada = [...visibles].sort(orden), max = ui.limite ?? paso();
  $('lista').innerHTML = ordenada.length ? ordenada.slice(0, max).map(filaHueco).join('')
    : vacio('Ningún hueco cumple estos filtros', '<button type="button" class="enlace" data-limpiar>Quitar filtros</button>');
  animarDesde = Infinity;      // las recargas automáticas (cada 2 min) no vuelven a animar la lista
  const quedan = ordenada.length - max;
  $('lista-pie').innerHTML = quedan > 0 ? `<button type="button" class="secundario" data-mas>Mostrar ${Math.min(quedan, paso())} más</button> `
    + `<span>quedan ${quedan.toLocaleString('es-CO')}; el CSV los trae todos</span>` : '';
}
const paso = () => (movil() ? 8 : 15);       // pocos a la vista (en el celular, debajo del mapa); el resto con «Mostrar más»

function abrirDetalle(id) {
  const h = D.huecos.find((x) => x.id_origen === id);
  if (!h) return;
  ui.seleccion = id;
  elegirPestana('atender');
  mapa.seleccionar(h); mapa.irA(h);
  mostrarDetalle(h);
  for (const b of $('lista').querySelectorAll('.fila')) b.setAttribute('aria-current', b.dataset.id === id);
  if (movil()) $('p-atender').scrollIntoView({behavior: 'smooth', block: 'start'});
  $('detalle').focus({preventScroll: true});
}
function cerrarDetalle() {
  ui.seleccion = null;
  mapa?.seleccionar(null);
  $('detalle').classList.add('oculto'); $('detalle').innerHTML = '';
  for (const id of ['lista', 'lista-pie', 'ayuda-lista']) $(id).classList.remove('oculto');
}
function mostrarDetalle(h) {
  for (const id of ['lista', 'lista-pie', 'ayuda-lista']) $(id).classList.add('oculto');
  const el = $('detalle'), editor = yo.rol === 'editor', camino = ['detectado', 'verificado', 'reparado'];
  const k = camino.indexOf(h.estado);
  const pasos = h.estado === 'descartado'
    ? `<p><span class="insignia" style="--c:var(--vv-descartado)">Descartado</span> <span class="sub">${esc(R.ESTADO.descartado.ayuda)}</span></p>`
    : `<ol class="pasos" style="--c:var(--vv-${h.estado})" aria-label="Estado: ${R.ESTADO[h.estado].nombre}">`
      + camino.map((e, i) => `<li class="${i <= k ? 'hecho' : ''}${i === k ? ' actual' : ''}">${R.ESTADO[e].nombre}</li>`).join('') + '</ol>';
  const filas = [
    ['Tipo', esc(R.nombreClase(h.clase)) + (h.clase === 'impacto_fuerte' ? ' <small>(nadie lo ha etiquetado todavía)</small>' : '')],
    ['Severidad', chipSev(h)],
    ['Detecciones', `${h.n_detecciones} ${h.n_detecciones === 1 ? 'vez' : 'veces'}`],
    ['Primera vez', `${R.fechaHora(h.primera_ts)} <small>(${R.hace(h.primera_ts)})</small>`],
    ['Última vez', `${R.fechaHora(h.ultima_ts)} <small>(${R.hace(h.ultima_ts)})</small>`],
  ];
  if (h.abierto) filas.push(['Lleva abierto', R.textoDias(h.diasAbierto)]);
  if (h.estado === 'reparado' && h.ts_estado) {
    filas.push(['Reparación', `registrada el ${R.fechaDia(h.ts_estado)} <small>(${R.textoDias(h.diasReparacion)} después de la primera detección)</small>`]);
  } else if (h.ts_estado) filas.push(['Último cambio', R.fechaHora(h.ts_estado)]);
  if (h.abierto) {
    filas.push(['Prioridad', `<b>${h.prioridad}</b> <small>= severidad ${h.nivelSev} × vía ${h.pesoVia} × ${Math.max(1, h.enTramo)} abierto(s) en el tramo</small>`]);
  }
  if (h.riesgoTramo != null) filas.push(['Riesgo del tramo', `${R.NIVELES_RIESGO[R.nivelRiesgo(h.riesgoTramo)]} (${R.porcentaje(h.riesgoTramo)})`]);
  filas.push(['Ubicación', `${h.lat.toFixed(5)}, ${h.lon.toFixed(5)} · <a href="https://www.google.com/maps/search/?api=1&query=${h.lat},${h.lon}" target="_blank" rel="noopener">Cómo llegar ↗</a>`]);
  if (h.instancia && !DEMO) filas.push(['Equipo', esc(h.instancia)]);
  el.innerHTML = '<button type="button" class="enlace" data-volver>← Volver a la lista</button>'
    + `<h3>${esc(h.lugar)} <small>${esc(h.etiqueta)}</small></h3>`
    + `<p class="sub">${esc([h.barrio, h.via !== '—' ? h.via : null].filter(Boolean).join(' · '))}</p>${pasos}`
    + `<dl class="datos">${filas.map(([a, b]) => `<dt>${a}</dt><dd>${b}</dd>`).join('')}</dl>`
    + '<button type="button" class="secundario" data-ver>Ver en el mapa</button><div id="pendientes"></div>'
    + (editor ? cambioHTML(h) : '<p class="sub" style="margin-top:.8rem">Solo lectura: los cambios de estado los hace el equipo.</p>');
  el.classList.remove('oculto');
  el.querySelector('[data-volver]').onclick = () => { const id = h.id_origen; cerrarDetalle(); $('lista').querySelector(`[data-id="${CSS.escape(id)}"]`)?.focus(); };
  el.querySelector('[data-ver]').onclick = () => { mapa.irA(h); if (movil()) $('mapa').scrollIntoView({behavior: 'smooth', block: 'center'}); };
  if (editor) conectarCambio(h);
  if (sb && !DEMO) {
    cambiosPendientes(sb, h.id_origen).then((p) => {
      if (p.length && ui.seleccion === h.id_origen && $('pendientes')) {
        $('pendientes').innerHTML = `<p class="pendiente">Cambio pedido: «${esc(R.ESTADO[p[0].estado]?.nombre || p[0].estado)}» `
          + `(${esc(R.hace(p[0].creado))}). Se aplica cuando la Pi sincronice.</p>`;
      }
    });
  }
}
function cambioHTML(h) {
  return '<div class="cambio"><b>Cambiar estado</b><div class="seg" role="radiogroup" aria-label="Nuevo estado" id="nuevo-estado">'
    + R.ESTADOS.map((e) => `<button type="button" role="radio" aria-checked="${e === h.estado}" data-e="${e}">${R.ESTADO[e].nombre}</button>`).join('')
    + '</div><input id="nota" placeholder="Nota (opcional): cuadrilla, observación…" maxlength="300">'
    + '<button type="button" id="b-cambiar" disabled>Enviar cambio</button>'
    + '<p class="sub">Queda pendiente hasta que la Pi sincronice (la base de la Pi manda).</p></div>';
}
function conectarCambio(h) {
  let elegido = h.estado;
  for (const b of $('nuevo-estado').querySelectorAll('button')) b.onclick = () => {
    elegido = b.dataset.e;
    for (const x of $('nuevo-estado').querySelectorAll('button')) x.setAttribute('aria-checked', x === b);
    $('b-cambiar').disabled = elegido === h.estado;
  };
  $('b-cambiar').onclick = async () => {
    if (DEMO) return toast(`DEMOSTRACIÓN: aquí no se envía nada. En la versión real, «${R.ESTADO[elegido].nombre}» queda pedido y la Pi lo aplica al sincronizar.`);
    $('b-cambiar').setAttribute('aria-busy', 'true');
    const {error} = await sb.from('cambios_remotos').insert({id_origen: h.id_origen, instancia: h.instancia, id_local: h.id_local,
      estado: elegido, nota: $('nota').value.trim() || null});
    $('b-cambiar').removeAttribute('aria-busy');
    if (error) return toast('No se guardó: ' + error.message);
    toast(`${h.etiqueta}: «${R.ESTADO[elegido].nombre}» enviado. Se verá cuando la Pi sincronice.`);
    mostrarDetalle(h);
  };
}

// ------------------------------------------------------------------ mapa: textos emergentes
function htmlHuecoCorto(id) {
  const h = D.huecos.find((x) => x.id_origen === id);
  return h ? `<b>${esc(h.lugar)}</b><br>${R.ESTADO[h.estado].nombre} · severidad ${esc(R.nombreSeveridad(h.severidad).toLowerCase())}` : '';
}
function htmlTramo(p) {
  const n = R.nivelRiesgo(p.p), l = R.lugar(p), ab = D.abiertosTramo.get(p.id) || 0;
  return `<p><b>${esc(l.titulo)}</b><br><small>${esc([l.barrio, l.via].filter(Boolean).join(' · '))}</small></p>`
    + `<p><i class="lin" style="background:var(--vv-r${n});height:5px"></i> Riesgo <b>${R.NIVELES_RIESGO[n].toLowerCase()}</b> (${R.porcentaje(p.p)})</p>`
    + `<p>${ab ? plural(ab, 'hueco abierto', 'huecos abiertos') + ' en este tramo' : 'Sin huecos abiertos registrados en este tramo'}</p>`
    + '<p><small>Probabilidad estimada por el modelo de que el tramo tenga un hueco que nadie ha reportado. No es una certeza.</small></p>';
}

// ------------------------------------------------------------------ tramos en riesgo
function tramosTop() {
  const c = D.corrida;
  $('ayuda-tramos').innerHTML = 'Probabilidad estimada de que el tramo tenga un hueco sin reportar: una guía para revisar, no una certeza.'
    + (c ? `<br><span class="chip">${esc(c.modelo)} · ${esc(c.version)} · ${R.fechaDia(c.fecha)}</span>` : '')
    + (c?.demo ? ' <span class="chip fuerte">DEMO: no es un resultado</span>' : '');
  if (!D.riesgo.length) {
    $('top').innerHTML = vacio('Aún no hay corridas del modelo de riesgo', 'Aparecen cuando se corre el modelo y la Pi sincroniza.');
    return;
  }
  const abiertos = (id) => D.abiertosTramo.get(id) || 0;
  const top = [...D.riesgo].sort((a, b) => b.probabilidad - a.probabilidad || abiertos(b.id_tramo) - abiertos(a.id_tramo)).slice(0, 10);
  $('top').innerHTML = top.map((r, i) => {
    const t = D.info.get(r.id_tramo), n = R.nivelRiesgo(r.probabilidad), ab = abiertos(r.id_tramo);
    const l = t ? R.lugar(t) : {titulo: `Tramo ${r.id_tramo}`, barrio: null, via: 'no está en el archivo de calles'};
    return `<li><button type="button" class="fila" data-tramo="${r.id_tramo}"><span class="num" style="--c:var(--vv-r${n})">${i + 1}</span>`
      + `<span><span class="fila-titulo">${esc(l.titulo)}</span><span class="fila-sub">${esc([l.barrio, l.via].filter(Boolean).join(' · '))}</span>`
      + `<span class="barra-riesgo" aria-hidden="true"><i style="width:${(r.probabilidad * 100).toFixed(1)}%;background:var(--vv-r${n})"></i></span>`
      + (ab ? `<span class="chips"><span class="chip fuerte">${plural(ab, 'hueco abierto', 'huecos abiertos')}</span></span>` : '')
      + `</span><span class="fila-der"><b>${R.porcentaje(r.probabilidad)}</b>${R.NIVELES_RIESGO[n]}</span></button></li>`;
  }).join('');
}

// ------------------------------------------------------------------ tendencia
function tendencia(base) {
  const r = vista.rango, ahora = Date.now(), hasta = r ? Math.min(r[1], ahora) : ahora;
  let desde = r && Number.isFinite(r[0]) ? r[0] : ahora - 11 * 7 * DIA;
  desde = Math.min(hasta, Math.max(desde, hasta - 25 * 7 * DIA));           // entre 1 y 26 semanas
  const sem = R.semanas(desde, hasta), nuevos = new Map(sem.map((k) => [k, 0])), rep = new Map(sem.map((k) => [k, 0]));
  for (const h of base) {
    const a = R.lunes(h.primera_ts);
    if (nuevos.has(a)) nuevos.set(a, nuevos.get(a) + 1);
    if (h.estado === 'reparado' && h.ts_estado) { const b = R.lunes(h.ts_estado); if (rep.has(b)) rep.set(b, rep.get(b) + 1); }
  }
  const nombres = sem.map((k) => `${Number(k.slice(8))} ${MESES[Number(k.slice(5, 7)) - 1]}`);
  const n = [...nuevos.values()], m = [...rep.values()], suma = (x) => x.reduce((s, v) => s + v, 0);
  $('ayuda-semana').textContent = `${sem.length === 1 ? 'Una semana' : `${sem.length} semanas`}. `
    + 'Si lo naranja supera a lo verde, aparecen más huecos de los que se reparan.';
  $('g-semana').setAttribute('aria-label', `Huecos nuevos y reparados por semana durante ${sem.length} semanas: `
    + `${suma(n)} nuevos y ${suma(m)} reparados. Los números están en «Ver los números».`);
  $('tabla-semana').innerHTML = '<table><thead><tr><th>Semana del</th><th class="n">Nuevos</th><th class="n">Reparados</th></tr></thead><tbody>'
    + nombres.map((x, i) => `<tr><td>${x}</td><td class="n">${n[i]}</td><td class="n">${m[i]}</td></tr>`).join('') + '</tbody></table>';
  const datos = {labels: nombres, datasets: [
    {label: 'Nuevos', data: n, backgroundColor: css('--vv-detectado'), borderRadius: 4, maxBarThickness: 16},
    {label: 'Reparados', data: m, backgroundColor: css('--vv-reparado'), borderRadius: 4, maxBarThickness: 16}]};
  if (grafico) { grafico.data = datos; grafico.update('none'); } else {
    Chart.defaults.color = css('--pico-muted-color');
    Chart.defaults.borderColor = css('--pico-muted-border-color');
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    grafico = new Chart($('g-semana'), {type: 'bar', data: datos, options: {maintainAspectRatio: false,
      animation: matchMedia('(prefers-reduced-motion: reduce)').matches ? false : {duration: 300},
      plugins: {legend: {position: 'bottom', labels: {boxWidth: 12, boxHeight: 12}},
        tooltip: {callbacks: {title: (it) => 'Semana del ' + it[0].label}}},
      scales: {y: {beginAtZero: true, ticks: {precision: 0}}, x: {grid: {display: false}, ticks: {maxRotation: 0, autoSkipPadding: 10}}}}});
  }
  donde(base);
}
function donde(base) {
  const ab = base.filter((h) => h.abierto), conBarrio = ab.filter((h) => h.barrio).length;
  const porBarrio = conBarrio > 0 && conBarrio >= ab.length / 2;
  const clave = (h) => (porBarrio ? h.barrio : h.calle);          // calle = nombre real en OSM (sin nombre: no cuenta)
  grupos = new Map();
  for (const h of ab) { const k = clave(h); if (k) grupos.set(k, [...(grupos.get(k) || []), h]); }
  const top = [...grupos.entries()].sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0], 'es')).slice(0, 6);
  $('h-donde').textContent = porBarrio ? 'Barrios con más huecos abiertos' : 'Calles con más huecos abiertos';
  if (!top.length) { $('donde').innerHTML = vacio('Sin huecos abiertos con estos filtros', ''); return; }
  $('donde').innerHTML = top.map(([k, l]) => `<li><button type="button" data-grupo="${esc(k)}" title="Ver en el mapa">`
    + `<span>${esc(k)}</span><b>${l.length}</b><span class="b"><i style="width:${(100 * l.length / top[0][1].length).toFixed(1)}%"></i></span></button></li>`).join('');
}

// ------------------------------------------------------------------ leyenda, entrada por partes y destino
function ponerLeyenda() {
  $('leyenda-resumen').innerHTML = leyendaResumen(ui.modo);
  $('leyenda-cuerpo').innerHTML = leyendaHTML(ui.modo, D.corrida);
}
/** Cifra que cuenta de 0 a su valor (formato es-CO). */
function contar(el) {
  const fin = Number(el.dataset.valor);
  if (QUIETO || el.dataset.valor === '' || !Number.isFinite(fin)) return;
  const t0 = performance.now(), dur = 900;
  const paso = (t) => {
    const p = Math.min(1, (t - t0) / dur);
    el.textContent = Math.round(fin * (1 - (1 - p) ** 3)).toLocaleString('es-CO');
    if (p < 1) requestAnimationFrame(paso);
  };
  requestAnimationFrame(paso);
}
/** La primera vez, la pantalla entra por partes: cifras (contando), filtros, mapa y panel. */
function entrada() {
  document.body.classList.remove('cargando');
  if (QUIETO) return;
  const partes = [...document.querySelectorAll('.cifra'), document.querySelector('.filtros'), $('mapa').closest('.tarjeta'),
    document.querySelector('.panel')];
  partes.forEach((el, i) => { el.style.setProperty('--i', i); el.classList.add('entra'); });
  for (const b of document.querySelectorAll('.cifra b')) contar(b);
}
/** tablero.html#riesgo · #tendencia · #atender (enlaces de la portada). */
function irAlDestino() {
  const destino = location.hash.slice(1);
  if (destino === 'riesgo' && D.riesgo.length) atajo({}, 'riesgo', 'tramos');
  else if (destino === 'tendencia') elegirPestana('tendencia');
}

// ------------------------------------------------------------------ controles
function elegirPestana(p) {
  for (const n of ['atender', 'tramos', 'tendencia']) {
    const t = $('t-' + n), sel = n === p;
    t.setAttribute('aria-selected', sel); t.tabIndex = sel ? 0 : -1; $('p-' + n).hidden = !sel;
  }
  if (p === 'tendencia') grafico?.resize();
}
function ponerModo(m) {
  if (m === 'riesgo' && !D.riesgo.length) return;
  ui.modo = m;
  mapa.ponerModo(m);
  for (const b of $('f-modo').querySelectorAll('button')) { b.setAttribute('aria-checked', b.dataset.m === m); b.tabIndex = b.dataset.m === m ? 0 : -1; }
  ponerLeyenda();
  $('k-riesgo').setAttribute('aria-pressed', m === 'riesgo');
}
function sincronizarControles() {
  const f = ui.filtro;
  for (const b of $('f-vista').querySelectorAll('button')) { b.setAttribute('aria-checked', b.dataset.v === f.vista); b.tabIndex = b.dataset.v === f.vista ? 0 : -1; }
  $('f-sev').value = f.sev; $('f-clase').value = f.clase; $('f-periodo').value = f.periodo;
  $('f-fechas').classList.toggle('oculto', f.periodo !== 'rango');
  $('f-desde').value = f.desde; $('f-hasta').value = f.hasta;
  const n = [f.sev, f.clase, f.periodo !== 'todo'].filter(Boolean).length;
  $('b-limpiar').classList.toggle('oculto', !n);
  $('n-filtros').textContent = n; $('n-filtros').classList.toggle('oculto', !n);
}
function cambiarFiltro(cambios) { Object.assign(ui.filtro, cambios); ui.limite = null; animarDesde = 0; sincronizarControles(); pintar(); }
function atajo(cambios, modo, pestana) {
  cerrarDetalle();
  Object.assign(ui.filtro, cambios); ui.limite = null; animarDesde = 0; ponerModo(modo); elegirPestana(pestana); sincronizarControles(); pintar();
}
/** Flechas dentro de un grupo de botones o pestañas (patrón de radio/pestañas accesible). */
function flechas(grupo, selector) {
  grupo.addEventListener('keydown', (e) => {
    const paso = {ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1}[e.key];
    const bs = [...grupo.querySelectorAll(selector)].filter((b) => !b.disabled), i = bs.indexOf(document.activeElement);
    if (!paso || i < 0) return;
    e.preventDefault();
    const s = bs[(i + paso + bs.length) % bs.length]; s.focus(); s.click();
  });
}

function conectarControles() {
  const hoy = new Date(Date.now() - 5 * 3600e3).toISOString().slice(0, 10);
  $('f-desde').max = hoy; $('f-hasta').max = hoy;
  for (const b of $('f-vista').querySelectorAll('button')) b.onclick = () => { cerrarDetalle(); cambiarFiltro({vista: b.dataset.v}); };
  for (const b of $('f-modo').querySelectorAll('button')) b.onclick = () => { ponerModo(b.dataset.m); };
  flechas($('f-vista'), 'button'); flechas($('f-modo'), 'button'); flechas(document.querySelector('.pestanas'), '[role="tab"]');
  $('f-sev').onchange = () => cambiarFiltro({sev: $('f-sev').value});
  $('f-clase').onchange = () => cambiarFiltro({clase: $('f-clase').value});
  $('f-periodo').onchange = () => cambiarFiltro({periodo: $('f-periodo').value});
  $('f-desde').onchange = $('f-hasta').onchange = () => cambiarFiltro({desde: $('f-desde').value, hasta: $('f-hasta').value});
  const limpiar = () => cambiarFiltro({sev: '', clase: '', periodo: 'todo', desde: '', hasta: ''});
  $('b-limpiar').onclick = limpiar;
  $('b-filtros').onclick = () => {
    const abierto = $('mas-filtros').classList.toggle('abierto');
    $('b-filtros').setAttribute('aria-expanded', abierto);
  };
  for (const n of ['atender', 'tramos', 'tendencia']) $('t-' + n).onclick = () => elegirPestana(n);
  $('k-abiertos').onclick = () => atajo({vista: 'abiertos', sev: ''}, 'huecos', 'atender');
  $('k-alta').onclick = () => atajo({vista: 'abiertos', sev: 'alta'}, 'huecos', 'atender');
  $('k-reparados').onclick = () => atajo({vista: 'reparados'}, 'huecos', 'atender');
  $('k-riesgo').onclick = () => { if (D.riesgo.length) atajo({}, 'riesgo', 'tramos'); };
  $('lista').onclick = (e) => {
    if (e.target.closest('[data-limpiar]')) return limpiar();
    const b = e.target.closest('[data-id]');
    if (b) abrirDetalle(b.dataset.id);
  };
  $('contexto').onclick = (e) => {
    const b = e.target.closest('[data-quitar]');
    if (!b) return;
    cambiarFiltro(b.dataset.quitar === 'periodo' ? {periodo: 'todo', desde: '', hasta: ''} : {[b.dataset.quitar]: ''});
  };
  $('lista-pie').onclick = (e) => {
    if (!e.target.closest('[data-mas]')) return;
    animarDesde = ui.limite ?? paso();
    ui.limite = animarDesde + paso();
    lista(vista.visibles);
  };
  $('top').onclick = (e) => {
    const b = e.target.closest('[data-tramo]');
    if (!b) return;
    const f = D.tramosRiesgo.features.find((x) => x.id === Number(b.dataset.tramo));
    for (const x of $('top').querySelectorAll('.fila')) x.setAttribute('aria-current', x === b);
    ponerModo('riesgo');
    if (f) { mapa.irATramo(f); mapa.abrirPopupTramo(f); }
    if (movil()) $('mapa').scrollIntoView({behavior: 'smooth', block: 'center'});
  };
  $('donde').onclick = (e) => {
    const b = e.target.closest('[data-grupo]');
    if (!b) return;
    ponerModo('huecos');
    mapa.ajustarA(grupos.get(b.dataset.grupo) || []);
    if (movil()) $('mapa').scrollIntoView({behavior: 'smooth', block: 'center'});
  };
}

// ------------------------------------------------------------------ descargar
function descargar(nombre, contenido, tipo) {
  const a = Object.assign(document.createElement('a'), {href: URL.createObjectURL(new Blob([contenido], {type: tipo})), download: nombre});
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
const cerrarMenu = () => { document.querySelector('.menu-exportar').open = false; };
const sello = () => new Date().toISOString().slice(0, 16).replace(/[:T-]/g, '') + (DEMO ? '_DEMO' : '');
// id_hueco (no id_local): así el CSV descargado sirve de base para «Importar reparaciones»
const COLUMNAS = [['id_hueco', (h) => h.id_local], ['instancia', (h) => h.instancia], ['estado', (h) => h.estado],
  ['tipo', (h) => h.clase], ['severidad', (h) => h.severidad || ''], ['detecciones', (h) => h.n_detecciones],
  ['calle', (h) => h.lugar], ['barrio', (h) => h.barrio || ''], ['tipo_via', (h) => h.via], ['lat', (h) => h.lat],
  ['lon', (h) => h.lon], ['id_tramo', (h) => h.id_tramo ?? ''], ['primera_deteccion_utc', (h) => h.primera_ts],
  ['ultima_deteccion_utc', (h) => h.ultima_ts], ['fecha_estado_utc', (h) => h.ts_estado || ''],
  ['prioridad', (h) => (h.abierto ? h.prioridad : '')]];
$('x-csv').onclick = (e) => {
  e.preventDefault(); cerrarMenu();
  const filas = [COLUMNAS.map((c) => c[0]).join(','), ...[...vista.visibles].sort(orden).map((h) => COLUMNAS.map(([, f]) => R.celdaCSV(f(h))).join(','))];
  descargar(`viaviva_huecos_${sello()}.csv`, '﻿' + filas.join('\r\n') + '\r\n', 'text/csv;charset=utf-8');
};
$('x-xlsx').onclick = async (e) => {
  e.preventDefault(); cerrarMenu();
  const XLSX = await import('https://cdn.sheetjs.com/xlsx-0.20.3/package/xlsx.mjs');
  const libro = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(libro, XLSX.utils.json_to_sheet([...vista.visibles].sort(orden)
    .map((h) => Object.fromEntries(COLUMNAS.map(([c, f]) => [c, f(h)])))), 'Huecos');
  XLSX.utils.book_append_sheet(libro, XLSX.utils.json_to_sheet(D.riesgo.map((r) => {
    const t = D.info.get(r.id_tramo), l = R.lugar(t);
    return {id_tramo: r.id_tramo, calle: t ? l.titulo : '', barrio: l.barrio || '', tipo_via: t ? l.via : '',
      probabilidad: r.probabilidad, nivel: R.NIVELES_RIESGO[R.nivelRiesgo(r.probabilidad)], huecos_abiertos: D.abiertosTramo.get(r.id_tramo) || 0};
  })), 'Riesgo por tramo');
  XLSX.utils.book_append_sheet(libro, XLSX.utils.aoa_to_sheet([['VÍA VIVA', DEMO ? 'DEMOSTRACIÓN: datos inventados' : ''],
    ['Generado', new Date().toLocaleString('es-CO', {timeZone: 'America/Bogota'})], ['Vista', $('contexto').textContent],
    ['Último dato', D.ultimoDato ? R.fechaHora(D.ultimoDato) : '—'],
    ['Corrida de riesgo', D.corrida ? `${D.corrida.modelo} ${D.corrida.version} (${R.fechaDia(D.corrida.fecha)})` : '—'], [],
    ['Estado', 'Huecos (con los filtros de severidad, tipo y periodo)'],
    ...R.ESTADOS.map((s) => [R.ESTADO[s].nombre, vista.base.filter((h) => h.estado === s).length])]), 'Resumen');
  XLSX.writeFile(libro, `viaviva_${sello()}.xlsx`);
};
$('x-pdf').onclick = (e) => { e.preventDefault(); cerrarMenu(); setTimeout(() => print(), 200); };

// ------------------------------------------------------------------ importar reparaciones (editores)
let cambiosCSV = [];
$('b-importar').onclick = () => { $('vista').innerHTML = ''; $('archivo').value = ''; $('b-enviar').disabled = true; $('d-importar').showModal(); };
$('x-plantilla').onclick = (e) => { e.preventDefault(); descargar('plantilla_reparaciones.csv', '﻿id_hueco,instancia,estado,fecha,nota\r\n', 'text/csv;charset=utf-8'); };
$('archivo').onchange = async () => {
  const archivo = $('archivo').files[0];
  if (!archivo) return;
  const r = R.validarReparaciones(R.leerCSV(await archivo.text()), D.huecos);
  cambiosCSV = r.cambios;
  $('vista').innerHTML = `<p>${plural(r.filas, 'fila', 'filas')} · ${plural(r.cambios.length, 'válida', 'válidas')} · <b>${plural(r.errores.length, 'error', 'errores')}</b></p>`
    + '<table>' + (r.errores.length ? r.errores.map(([n, m]) => `<tr><td>Fila ${n}</td><td>${esc(m)}</td></tr>`).join('')
      : r.cambios.map((c) => `<tr><td>#${c.id_local}</td><td>${R.ESTADO[c.estado].nombre}</td><td>${esc(c.nota || '')}</td></tr>`).join('')) + '</table>';
  $('b-enviar').disabled = r.errores.length > 0 || !r.cambios.length;
};
$('b-enviar').onclick = async () => {
  if (DEMO) { $('d-importar').close(); return toast(`DEMOSTRACIÓN: el archivo está bien (${plural(cambiosCSV.length, 'cambio', 'cambios')}), pero aquí no se envía nada.`); }
  const {error} = await sb.from('cambios_remotos').insert(cambiosCSV);
  toast(error ? 'No se envió: ' + error.message : `${plural(cambiosCSV.length, 'cambio enviado', 'cambios enviados')}; se aplican cuando la Pi sincronice.`);
  $('d-importar').close();
};

iniciar();
