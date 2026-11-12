// VÍA VIVA · carga de datos del tablero en línea: Supabase (con sesión; RLS por rol) o datos de PRUEBA simulados en el
// navegador (acceso público del prototipo).
// `preparar` calcula una sola vez lo que la interfaz necesita (lugar legible, prioridad, días hasta reparar…).
import {ABIERTOS, dias, lugar, ms, nivelSeveridad, nombrarVecinos, pesoTransito} from './reglas.js';

const PAGINA = 1000;        // Supabase devuelve como máximo 1 000 filas por consulta (Project Settings → API → Max rows)
const DIA = 864e5;
const iso = (t) => new Date(t).toISOString();

/** Calles (tramos de OSM) de `viaviva nube preparar`. `demo: true` = archivo de herramientas/tramos_demo.py. */
export async function cargarTramos() {
  try {
    const r = await fetch('datos/tramos.geojson');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const g = await r.json();
    return {type: 'FeatureCollection', features: nombrarVecinos(g.features || []), demo: Boolean(g.demo), fuente: g.fuente || ''};
  } catch (e) {
    return {type: 'FeatureCollection', features: [], demo: false, fuente: '', error: e.message};
  }
}

/**
 * Lee TODAS las filas, página por página. Sin esto la consulta se cortaba en silencio en 1 000 filas: con 5 775 tramos,
 * el top-10 de riesgo y la cifra de tramos críticos salían de una muestra incompleta. Se sigue hasta una página vacía,
 * así funciona aunque alguien cambie el límite del proyecto.
 */
export async function leerTodo(armar, maxPaginas = 50) {
  const filas = [];
  for (let i = 0; i < maxPaginas; i++) {
    const {data, error} = await armar().range(filas.length, filas.length + PAGINA - 1);
    if (error) throw error;
    if (!data?.length) return filas;
    filas.push(...data);
  }
  return filas;
}

export async function cargarSupabase(sb) {
  const [huecos, riesgo] = await Promise.all([
    leerTodo(() => sb.from('huecos_publicos').select('*').order('ultima_ts', {ascending: false}).order('id_origen')),
    leerTodo(() => sb.from('riesgo_ultimo').select('id_tramo,probabilidad,rango,modelo,version_modelo,fecha_calculo')
      .order('probabilidad', {ascending: false}).order('id_tramo')),
  ]);
  return {huecos, riesgo};
}

/** Pedidos de cambio que la Pi todavía no aplica (para avisar en el detalle de un hueco). */
export async function cambiosPendientes(sb, idOrigen) {
  const {data, error} = await sb.from('cambios_remotos').select('estado,autor,creado')
    .eq('id_origen', idOrigen).eq('aplicado', false).order('creado', {ascending: false});
  return error ? [] : data;
}

/**
 * Datos de PRUEBA simulados para el acceso público del prototipo. Semilla fija: siempre los mismos. El riesgo no se recorta
 * (antes el tope de 0,97 hacía que el top-10 entero empatara en 97 %) y los huecos caen más en los tramos de más
 * riesgo, para que el mapa se parezca a un caso real. Nada de esto es un resultado.
 */
export function datosPrueba(tramos, ahora = Date.now()) {
  let s = 7;
  const azar = () => (s = (s * 16807) % 2147483647) / 2147483647;
  const lista = tramos.features.filter((t) => t.geometry?.coordinates?.length >= 2);
  const riesgo = lista.map((t) => {
    const peso = pesoTransito(t.properties?.t), x = 0.95 * azar() ** 6;     // nunca 100 %
    const p = peso === 3 ? x + (1 - x) * 0.3 : peso === 2 ? x + (1 - x) * 0.12 : x;
    return {id_tramo: t.id, probabilidad: Math.round(p * 1000) / 1000, modelo: 'bosque', version_modelo: 'PRUEBA',
      fecha_calculo: iso(ahora - DIA)};
  });
  const pTramo = new Map(riesgo.map((r) => [r.id_tramo, r.probabilidad]));
  const elegir = () => {
    for (let i = 0; i < 1000; i++) {
      const t = lista[Math.floor(azar() * lista.length)];
      if (azar() < 0.1 + 0.9 * pTramo.get(t.id)) return t;
    }
    return lista[0];
  };
  const huecos = lista.length ? Array.from({length: 140}, (_, i) => {
    const t = elegir(), c = t.geometry.coordinates[Math.floor(azar() * t.geometry.coordinates.length)];
    const u = azar(), estado = u < 0.45 ? 'detectado' : u < 0.7 ? 'verificado' : u < 0.92 ? 'reparado' : 'descartado';
    const v = azar(), severidad = v < 0.3 ? 'alta' : v < 0.72 ? 'media' : 'baja';
    const primera = ahora - (1 + azar() * 80) * DIA;
    const tsEstado = estado === 'detectado' ? null
      : Math.min(ahora - 3600e3, primera + (0.5 + azar() * (estado === 'reparado' ? 24 : 5)) * DIA);
    const ultima = primera + azar() * ((tsEstado ?? ahora) - primera);
    return {id_origen: 'prueba|' + (i + 1), instancia: 'prueba', id_local: i + 1, lat: c[1], lon: c[0],
      clase: azar() < 0.75 ? 'hueco' : 'impacto_fuerte', severidad, n_detecciones: 1 + Math.floor(azar() ** 2 * 6),
      estado, id_tramo: t.id, primera_ts: iso(primera), ultima_ts: iso(ultima), ts_estado: tsEstado && iso(tsEstado),
      recibido: iso(ahora - 2 * 3600e3)};
  }) : [];
  return {huecos, riesgo};
}

/** Une huecos, riesgo y calles, y calcula lo derivado una sola vez. */
export function preparar(huecosCrudos, riesgoCrudo, tramos, ahora = Date.now()) {
  const info = new Map(tramos.features.map((f) => [f.id, f.properties || {}]));
  const riesgo = [...riesgoCrudo].sort((a, b) => b.probabilidad - a.probabilidad || a.id_tramo - b.id_tramo);
  const pTramo = new Map(riesgo.map((r) => [r.id_tramo, r.probabilidad]));
  const vecesNumero = new Map(), abiertosTramo = new Map();
  for (const h of huecosCrudos) {
    vecesNumero.set(h.id_local, (vecesNumero.get(h.id_local) || 0) + 1);
    if (ABIERTOS.has(h.estado) && h.id_tramo != null) abiertosTramo.set(h.id_tramo, (abiertosTramo.get(h.id_tramo) || 0) + 1);
  }
  let ultimoDato = null;
  const huecos = huecosCrudos.map((h) => {
    const t = info.get(h.id_tramo), l = lugar(t), abierto = ABIERTOS.has(h.estado);
    const nivelSev = nivelSeveridad(h.severidad, h.clase), pesoVia = pesoTransito(t?.t);
    const enTramo = h.id_tramo != null ? abiertosTramo.get(h.id_tramo) || 0 : 0;
    // «recibido» solo se pone al insertar (un upsert no lo cambia): el último dato es lo más reciente de los tres
    for (const t of [ms(h.recibido), ms(h.ultima_ts), ms(h.ts_estado)]) {
      if (Number.isFinite(t) && (ultimoDato === null || t > ultimoDato)) ultimoDato = t;
    }
    return {...h, abierto, lugar: l.titulo, calle: t?.n || null, barrio: l.barrio, via: l.via, tipoVia: t?.t || null,
      // el número del hueco solo es único dentro de cada equipo: si se repite, se agrega el equipo
      etiqueta: `#${h.id_local}` + (vecesNumero.get(h.id_local) > 1 ? ` (${h.instancia})` : ''),
      nivelSev, pesoVia, enTramo, prioridad: abierto ? nivelSev * pesoVia * Math.max(1, enTramo) : 0,
      riesgoTramo: pTramo.get(h.id_tramo) ?? null,
      inicio: ms(h.primera_ts), fin: Math.max(ms(h.ultima_ts), ms(h.ts_estado) || 0),
      diasAbierto: abierto ? dias(h.primera_ts, ahora) : null,
      diasReparacion: h.estado === 'reparado' && h.ts_estado ? Math.max(0, dias(h.primera_ts, h.ts_estado)) : null};
  });
  const conRiesgo = tramos.features.filter((f) => pTramo.has(f.id))
    .map((f) => ({...f, properties: {...f.properties, p: pTramo.get(f.id), abiertos: abiertosTramo.get(f.id) || 0}}));
  const r0 = riesgo[0];
  const corrida = r0 ? {modelo: r0.modelo, version: r0.version_modelo, fecha: r0.fecha_calculo,
    demo: /DEMO|PRUEBA|SINT[EÉ]TICO/i.test(r0.version_modelo || '')} : null;   // corrida de prueba: no es un resultado
  return {huecos, riesgo, corrida, ultimoDato, abiertosTramo, info,
    tramosRiesgo: {type: 'FeatureCollection', features: conRiesgo}};
}
