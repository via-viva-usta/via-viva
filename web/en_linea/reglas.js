// VÍA VIVA · vocabulario y reglas del tablero en línea (sin dependencias: se prueba con Node).
// Una sola fuente para nombres, niveles, prioridad, fechas y CSV. Las fórmulas son las mismas del tablero local
// (viaviva/web/tablero.html y viaviva/almacen.py): si se cambian aquí, cambiarlas allá.

// ------------------------------------------------------------------ estados de un hueco
export const ESTADOS = ['detectado', 'verificado', 'reparado', 'descartado'];
export const ABIERTOS = new Set(['detectado', 'verificado']);
export const ESTADO = {
  detectado: {nombre: 'Detectado', ayuda: 'lo sintió el sensor del carro; falta verificarlo en sitio'},
  verificado: {nombre: 'Verificado', ayuda: 'alguien del equipo confirmó en sitio que existe'},
  reparado: {nombre: 'Reparado', ayuda: 'se registró la reparación'},
  descartado: {nombre: 'Descartado', ayuda: 'no era un hueco (p. ej., un resalto o una tapa)'},
};

// ------------------------------------------------------------------ tipo y severidad
// En la tabla huecos la clase es «hueco» si alguien etiquetó alguna detección así; si no, «impacto_fuerte».
export const CLASE = {hueco: 'Hueco', impacto_fuerte: 'Golpe sin clasificar'};
export const nombreClase = (c) => CLASE[c] || (c ? String(c).replaceAll('_', ' ') : '—');
export const SEVERIDADES = ['alta', 'media', 'baja'];
export const SEVERIDAD = {alta: 'Alta', media: 'Media', baja: 'Baja'};
export const nombreSeveridad = (s) => SEVERIDAD[s] || 'Sin dato';

// ------------------------------------------------------------------ riesgo por tramo
export const CORTES_RIESGO = [0.2, 0.4, 0.6, 0.8];          // mismos cortes que el tablero local
export const NIVELES_RIESGO = ['Muy bajo', 'Bajo', 'Medio', 'Alto', 'Muy alto'];
export const RIESGO_ALTO = 0.6;                             // «tramos con riesgo alto» = Alto + Muy alto
export const nivelRiesgo = (p) => CORTES_RIESGO.filter((c) => p >= c).length;   // 0 … 4
export const porcentaje = (p) => Math.round(p * 100) + ' %';

// ------------------------------------------------------------------ tipo de vía (etiqueta highway de OSM)
const VIAS = {motorway: 'Autopista', trunk: 'Vía troncal', primary: 'Vía principal', secondary: 'Vía secundaria',
  tertiary: 'Vía terciaria', residential: 'Calle residencial', living_street: 'Calle residencial',
  unclassified: 'Vía sin clasificar', service: 'Vía de servicio', track: 'Trocha', road: 'Vía'};
const partesVia = (tipo) => String(tipo || '').split(';').map((p) => p.trim().toLowerCase().replace(/_link$/, '')).filter(Boolean);
export const nombreVia = (tipo) => VIAS[partesVia(tipo)[0]] || (tipo ? 'Vía' : '—');

// ------------------------------------------------------------------ prioridad de atención
// prioridad = nivel de severidad (1–3) × peso del tránsito (1–3) × huecos abiertos en el mismo tramo.
export function nivelSeveridad(sev, clase) {
  return {alta: 3, media: 2, baja: 1}[sev] ?? {hueco: 3, impacto_fuerte: 3, resalto: 1, vehiculo_varado: 1}[clase] ?? 2;
}
export function pesoTransito(tipo) {
  let mejor = 1;
  for (const t of partesVia(tipo)) mejor = Math.max(mejor, ['motorway', 'trunk', 'primary'].includes(t) ? 3
    : ['secondary', 'tertiary'].includes(t) ? 2 : 1);
  return mejor;
}

// ------------------------------------------------------------------ lugar legible
// Un tramo sin nombre en OSM no se muestra como «tramo 128653127»: se dice junto a qué calle está (propiedad `c`,
// de nombrarVecinos), qué tipo de vía es y en qué barrio.
export function lugar(info) {
  const via = nombreVia(info?.t);
  const titulo = info?.n || (info?.c ? `Sin nombre, junto a ${info.c}` : info?.t ? `${via} sin nombre` : 'Ubicación sin tramo');
  return {titulo, barrio: info?.b || null, via};
}

/** Pone `c` («Calle 2 y Carrera 5») a cada tramo sin nombre: las calles con nombre que pasan por sus extremos. O(puntos). */
export function nombrarVecinos(features) {
  const clave = (p) => p[0].toFixed(5) + ',' + p[1].toFixed(5);
  const porPunto = new Map();
  for (const f of features) {
    const n = f.properties?.n, c = f.geometry?.coordinates;
    if (!n || !c) continue;
    for (const p of c) porPunto.set(clave(p), (porPunto.get(clave(p)) || new Set()).add(n));
  }
  for (const f of features) {
    const c = f.geometry?.coordinates;
    if (f.properties?.n || !c?.length) continue;
    const nombres = new Set([...(porPunto.get(clave(c[0])) || []), ...(porPunto.get(clave(c[c.length - 1])) || [])]);
    // los nombres más cortos primero: «Calle 2» orienta más que «Avenida Paseo Quintana - Prados de San Luis - …»
    if (nombres.size) f.properties.c = [...nombres].sort((a, b) => a.length - b.length || a.localeCompare(b, 'es')).slice(0, 2).join(' y ');
  }
  return features;
}

// ------------------------------------------------------------------ fechas (Tunja = UTC-5 todo el año)
const ZONA = 'America/Bogota', DESFASE_MS = -5 * 3600e3, DIA_MS = 864e5;
export const ms = (ts) => (ts ? new Date(ts).getTime() : NaN);
export const fechaHora = (ts) => (ts ? new Date(ts).toLocaleString('es-CO', {timeZone: ZONA, day: 'numeric',
  month: 'short', hour: 'numeric', minute: '2-digit'}) : '—');
export const fechaDia = (ts) => (ts ? new Date(ts).toLocaleDateString('es-CO', {timeZone: ZONA, day: 'numeric',
  month: 'short', year: 'numeric'}) : '—');
/** 'AAAA-MM-DD' de un campo de fecha → instante en hora de Tunja (inicio o fin de ese día). */
export const diaLocal = (v, finDelDia = false) => new Date(`${v}T${finDelDia ? '23:59:59.999' : '00:00:00'}-05:00`);
/** Lunes (hora de Tunja) de la semana de `ts`, como 'AAAA-MM-DD'. */
export function lunes(ts) {
  const d = new Date(ms(ts) + DESFASE_MS);
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() - (d.getUTCDay() + 6) % 7))
    .toISOString().slice(0, 10);
}
/** Semanas consecutivas (lunes) de `desde` a `hasta`, sin huecos: una semana sin datos vale 0, no desaparece. */
export function semanas(desde, hasta) {
  const lista = [], fin = lunes(hasta);
  for (let k = lunes(desde); k <= fin && lista.length < 60; k = new Date(ms(k + 'T00:00:00Z') + 7 * DIA_MS).toISOString().slice(0, 10)) {
    lista.push(k);
  }
  return lista;
}
export const dias = (a, b) => (ms(b) - ms(a)) / DIA_MS;
export function hace(ts, ahora = Date.now()) {
  const d = (ahora - ms(ts)) / DIA_MS;
  if (!Number.isFinite(d)) return '—';
  if (d < 1 / 24) return 'hace minutos';
  if (d < 1) return `hace ${Math.round(d * 24)} h`;
  if (d < 2) return 'ayer';
  if (d < 14) return `hace ${Math.floor(d)} días`;
  if (d < 60) return `hace ${Math.floor(d / 7)} semanas`;
  return `hace ${Math.floor(d / 30)} meses`;
}
export const textoDias = (d) => (d < 1 ? 'menos de 1 día' : `${Math.round(d)} día${Math.round(d) === 1 ? '' : 's'}`);

// ------------------------------------------------------------------ CSV (RFC 4180, separador , o ;)
export function celdaCSV(v) {
  const s = v === null || v === undefined ? '' : String(v);
  return /[",;\r\n]/.test(s) ? '"' + s.replaceAll('"', '""') + '"' : s;
}
export function leerCSV(texto) {
  texto = String(texto).replace(/^﻿/, '');
  const primera = texto.split(/\r?\n/, 1)[0];
  const sep = primera.split(';').length > primera.split(',').length ? ';' : ',';
  const filas = [];
  let fila = [], celda = '', comillas = false;
  for (let i = 0; i < texto.length; i++) {
    const c = texto[i];
    if (comillas) {
      if (c !== '"') celda += c;
      else if (texto[i + 1] === '"') { celda += '"'; i++; } else comillas = false;
    } else if (c === '"') comillas = true;
    else if (c === sep) { fila.push(celda); celda = ''; } else if (c === '\n' || c === '\r') {
      if (c === '\r' && texto[i + 1] === '\n') i++;
      fila.push(celda); filas.push(fila); fila = []; celda = '';
    } else celda += c;
  }
  if (celda !== '' || fila.length) { fila.push(celda); filas.push(fila); }
  return filas.map((f) => f.map((x) => x.trim())).filter((f) => f.some((x) => x !== ''));
}

/**
 * Revisa un CSV de reparaciones (id_hueco, estado, fecha, nota y, si hace falta, instancia) contra los huecos cargados.
 * El número del hueco solo es único dentro de cada equipo (instancia): si hay dos #12, se pide la columna instancia.
 * Devuelve {cambios, errores, filas}; solo se envía si no hay errores.
 */
export function validarReparaciones(filas, huecos, hoy = new Date()) {
  const errores = [], cambios = [];
  if (!filas.length) return {cambios, errores: [[1, 'el archivo está vacío']], filas: 0};
  const cab = filas[0].map((c) => c.toLowerCase());
  const col = (n) => cab.indexOf(n), dato = (f, n) => (col(n) >= 0 ? f[col(n)] || '' : '');
  if (col('id_hueco') < 0) return {cambios, errores: [[1, 'falta la columna id_hueco']], filas: filas.length - 1};
  const porId = new Map();
  for (const h of huecos) porId.set(h.id_local, [...(porId.get(h.id_local) || []), h]);
  const vistos = new Set();
  filas.slice(1).forEach((f, k) => {
    const n = k + 2, crudo = dato(f, 'id_hueco'), id = Number(crudo.replace(/^#/, '')), inst = dato(f, 'instancia');
    const est = (dato(f, 'estado') || 'reparado').toLowerCase(), fTexto = dato(f, 'fecha');
    let cand = Number.isInteger(id) ? porId.get(id) || [] : [];
    if (inst) cand = cand.filter((h) => h.instancia === inst);
    if (!cand.length) return errores.push([n, `el hueco «${crudo}» no existe${inst ? ' en ' + inst : ''}`]);
    if (cand.length > 1) return errores.push([n, `hay ${cand.length} huecos #${id} (${cand.map((h) => h.instancia).join(', ')}): agregue la columna instancia`]);
    const h = cand[0];
    if (vistos.has(h.id_origen)) return errores.push([n, `el hueco #${id} está repetido`]);
    vistos.add(h.id_origen);
    if (!ESTADOS.includes(est)) return errores.push([n, `estado «${est}» no válido (use ${ESTADOS.join(', ')})`]);
    if (est === 'reparado' && !fTexto) return errores.push([n, 'falta la fecha de la reparación (AAAA-MM-DD)']);
    if (fTexto) {
      const fe = diaLocal(fTexto);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(fTexto) || Number.isNaN(fe.getTime())) return errores.push([n, `fecha «${fTexto}»: use AAAA-MM-DD`]);
      if (fe > hoy) return errores.push([n, `la fecha ${fTexto} es futura`]);
    }
    const nota = [fTexto ? `${est === 'reparado' ? 'reparado' : 'fecha'} el ${fTexto}` : '', dato(f, 'nota')]
      .filter(Boolean).join(' · ').slice(0, 300) || null;
    cambios.push({id_origen: h.id_origen, instancia: h.instancia, id_local: h.id_local, estado: est, origen: 'csv', nota});
  });
  return {cambios, errores, filas: filas.length - 1};
}
