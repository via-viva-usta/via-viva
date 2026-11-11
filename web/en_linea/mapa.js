// VÍA VIVA · mapa del tablero en línea (MapLibre GL + OpenFreeMap).
// Dos modos para que los colores no se mezclen (antes un hueco rojo se perdía sobre una calle roja):
//   «huecos» → calles sin colorear; puntos por estado (relleno = abierto, anillo = cerrado), tamaño = severidad.
//   «riesgo» → calles por nivel de riesgo (lo bajo casi no se ve); huecos como puntos oscuros de referencia.
import * as maplibregl from 'https://cdn.jsdelivr.net/npm/maplibre-gl@6.17.0/dist/maplibre-gl.mjs';
import {CORTES_RIESGO, ESTADO, NIVELES_RIESGO, fechaDia} from './reglas.js';

export const TUNJA = [[-73.385, 5.505], [-73.340, 5.575]];      // zona urbana (igual que el mapa ciudadano)
const VACIO = {type: 'FeatureCollection', features: []};
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const oscuro = () => document.documentElement.dataset.theme === 'dark';
const estilo = () => 'https://tiles.openfreemap.org/styles/' + (oscuro() ? 'dark' : 'positron');
const pasos = (valores) => CORTES_RIESGO.flatMap((c, i) => [c, valores[i + 1]]);

class BotonCiudad {                     // control «ver toda la ciudad» junto al zoom
  constructor(alTocar) { this.alTocar = alTocar; }
  onAdd() {
    this.div = document.createElement('div');
    this.div.className = 'maplibregl-ctrl maplibregl-ctrl-group';
    this.div.innerHTML = '<button type="button" class="ctrl-ciudad" title="Ver toda la ciudad" aria-label="Ver toda la ciudad">'
      + '<svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"><path d="M3 8V3h5M17 8V3h-5M3 12v5h5M17 12v5h-5" '
      + 'fill="none" stroke="currentColor" stroke-width="2"/></svg></button>';
    this.div.firstChild.onclick = this.alTocar;
    return this.div;
  }
  onRemove() { this.div.remove(); }
}

export class Mapa {
  /** @param {{alTocarHueco: Function, htmlTramo: Function, htmlHuecoCorto: Function}} cb */
  constructor(div, cb) {
    this.cb = cb; this.modo = 'huecos'; this.datos = {tramos: VACIO, huecos: VACIO, sel: VACIO};
    this.m = new maplibregl.Map({container: div, style: estilo(), bounds: TUNJA, fitBoundsOptions: {padding: 16},
      attributionControl: {compact: true}, canvasContextAttributes: {preserveDrawingBuffer: true},   // para imprimir
      // en el celular un dedo desplaza la página y dos mueven el mapa (si no, el mapa «atrapa» el desplazamiento)
      cooperativeGestures: matchMedia('(pointer: coarse)').matches});
    this.m.addControl(new maplibregl.NavigationControl({showCompass: false}), 'top-right');
    this.m.addControl(new BotonCiudad(() => this.verCiudad()), 'top-right');
    this.m.on('style.load', () => this.capas());
    // Los eventos de capa se registran UNA vez (sobreviven a setStyle). Antes se registraban en cada cambio de tema
    // y un clic abría el detalle dos, tres… veces.
    this.m.on('click', 'huecos', (e) => cb.alTocarHueco(e.features[0].properties.id));
    this.m.on('click', 'riesgo', (e) => {
      if (this.m.queryRenderedFeatures(e.point, {layers: ['huecos']}).length) return;   // el hueco tiene prioridad
      this.popup?.remove();
      this.popup = new maplibregl.Popup({maxWidth: '280px'}).setLngLat(e.lngLat)
        .setHTML(cb.htmlTramo(e.features[0].properties)).addTo(this.m);
    });
    const flotante = new maplibregl.Popup({closeButton: false, closeOnClick: false, offset: 12, className: 'pop-corto'});
    for (const capa of ['huecos', 'riesgo']) {
      this.m.on('mouseenter', capa, () => { this.m.getCanvas().style.cursor = 'pointer'; });
      this.m.on('mouseleave', capa, () => { this.m.getCanvas().style.cursor = ''; flotante.remove(); });
    }
    if (matchMedia('(hover: hover)').matches) {
      this.m.on('mousemove', 'huecos', (e) => flotante.setLngLat(e.features[0].geometry.coordinates)
        .setHTML(cb.htmlHuecoCorto(e.features[0].properties.id)).addTo(this.m));
    }
  }

  capas() {
    const m = this.m;
    m.addSource('tramos', {type: 'geojson', data: this.datos.tramos});
    m.addLayer({id: 'riesgo', type: 'line', source: 'tramos',
      layout: {'line-cap': 'round', 'line-join': 'round', 'line-sort-key': ['get', 'p']},
      paint: {
        'line-color': ['step', ['get', 'p'], css('--vv-r0'), ...pasos(['', css('--vv-r1'), css('--vv-r2'), css('--vv-r3'), css('--vv-r4')])],
        'line-width': ['interpolate', ['linear'], ['zoom'],
          12, ['step', ['get', 'p'], 0.5, ...pasos([0, 1, 1.6, 2.6, 3.4])],
          17, ['step', ['get', 'p'], 1.5, ...pasos([0, 3, 4.5, 7, 9])]],
        'line-opacity': ['step', ['get', 'p'], 0.5, CORTES_RIESGO[0], 0.95], 'line-opacity-transition': {duration: 600}}});
    m.addSource('huecos', {type: 'geojson', data: this.datos.huecos});
    m.addLayer({id: 'huecos', type: 'circle', source: 'huecos', layout: {'circle-sort-key': ['get', 'orden']},
      paint: {'circle-opacity': 0, 'circle-stroke-opacity': 0, 'circle-opacity-transition': {duration: 700},
        'circle-stroke-opacity-transition': {duration: 700}}});
    m.addSource('seleccion', {type: 'geojson', data: this.datos.sel});
    m.addLayer({id: 'seleccion', type: 'circle', source: 'seleccion', paint: {'circle-radius': 17,
      'circle-color': 'rgba(0,0,0,0)', 'circle-stroke-color': css('--pico-primary'), 'circle-stroke-width': 3}});
    // un instante después: así MapLibre anima la opacidad de 0 a 1 (los datos entran con un fundido)
    setTimeout(() => this.aplicarModo(), 120);
  }

  pinturaHuecos() {
    if (this.modo === 'riesgo') {       // referencia discreta: no compite con el color de las calles
      return {'circle-color': css('--vv-punto-ref'), 'circle-stroke-color': css('--vv-borde-punto'), 'circle-stroke-width': 1,
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 11, 2, 16, 4.5], 'circle-opacity': 0.85, 'circle-stroke-opacity': 0.85};
    }
    const tam = ['match', ['get', 'severidad'], 'alta', 8, 'media', 6.5, 'baja', 5, 6];   // sin dato: intermedio
    return {
      'circle-color': ['case', ['get', 'abierto'],
        ['match', ['get', 'estado'], 'verificado', css('--vv-verificado'), css('--vv-detectado')], css('--vv-fondo-punto')],
      'circle-stroke-color': ['case', ['get', 'abierto'], css('--vv-borde-punto'),
        ['match', ['get', 'estado'], 'reparado', css('--vv-reparado'), css('--vv-descartado')]],
      'circle-stroke-width': ['case', ['get', 'abierto'], 1.5, 2.5],
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 11, ['*', 0.55, tam], 15, tam, 18, ['*', 1.6, tam]],
      'circle-opacity': 1, 'circle-stroke-opacity': 1};
  }

  aplicarModo() {
    if (!this.m.getLayer('huecos')) return;
    this.m.setLayoutProperty('riesgo', 'visibility', this.modo === 'riesgo' ? 'visible' : 'none');
    for (const [k, v] of Object.entries(this.pinturaHuecos())) this.m.setPaintProperty('huecos', k, v);
  }

  ponerModo(modo) { this.modo = modo; this.popup?.remove(); this.aplicarModo(); }
  ponerTramos(fc) { this.datos.tramos = fc; this.m.getSource('tramos')?.setData(fc); }
  ponerHuecos(lista) {
    this.datos.huecos = {type: 'FeatureCollection', features: lista.map((h) => ({type: 'Feature',
      properties: {id: h.id_origen, estado: h.estado, abierto: h.abierto, severidad: h.severidad || 'sin_dato',
        orden: (h.abierto ? 10 : 0) + h.nivelSev},              // lo abierto y severo se dibuja encima
      geometry: {type: 'Point', coordinates: [h.lon, h.lat]}}))};
    this.m.getSource('huecos')?.setData(this.datos.huecos);
  }
  seleccionar(h) {
    this.datos.sel = h ? {type: 'FeatureCollection', features: [{type: 'Feature', properties: {},
      geometry: {type: 'Point', coordinates: [h.lon, h.lat]}}]} : VACIO;
    this.m.getSource('seleccion')?.setData(this.datos.sel);
  }
  irA(h) { this.m.flyTo({center: [h.lon, h.lat], zoom: Math.max(this.m.getZoom(), 16.5), essential: true}); }
  irATramo(f) {
    const c = f.geometry.coordinates;
    this.m.fitBounds(c.reduce((b, p) => b.extend(p), new maplibregl.LngLatBounds(c[0], c[0])), {padding: 80, maxZoom: 17});
  }
  ajustarA(lista) {
    if (!lista.length) return;
    const b = lista.reduce((b, h) => b.extend([h.lon, h.lat]), new maplibregl.LngLatBounds([lista[0].lon, lista[0].lat], [lista[0].lon, lista[0].lat]));
    this.m.fitBounds(b, {padding: 60, maxZoom: 16.5});
  }
  abrirPopupTramo(f) {
    const c = f.geometry.coordinates, medio = c[Math.floor(c.length / 2)];
    this.popup?.remove();
    this.popup = new maplibregl.Popup({maxWidth: '280px'}).setLngLat(medio).setHTML(this.cb.htmlTramo(f.properties)).addTo(this.m);
  }
  verCiudad() { this.m.fitBounds(TUNJA, {padding: 16}); }
  cambiarTema() { this.m.setStyle(estilo(), {diff: false}); }     // 'style.load' vuelve a poner las capas
  redimensionar() { this.m.resize(); }
}

/** Leyenda en una línea (lo que se ve sin abrir): cada color dice qué significa. */
export function leyendaResumen(modo) {
  if (modo === 'riesgo') {
    return [0, 2, 4].map((n) => `<span class="ley-item"><i class="lin" style="background:var(--vv-r${n});height:${[2, 3, 4, 5, 6][n]}px"></i>`
      + `${NIVELES_RIESGO[n]}</span>`).join('');
  }
  return [['detectado', true], ['verificado', true], ['reparado', false]].map(([e, lleno]) =>
    `<span class="ley-item"><i class="pt${lleno ? '' : ' anillo'}" style="--c:var(--vv-${e})"></i>${ESTADO[e].nombre}</span>`).join('');
}

/** Leyenda completa del modo actual (al abrir «Leyenda»). */
export function leyendaHTML(modo, corrida) {
  if (modo === 'riesgo') {
    const filas = [4, 3, 2, 1, 0].map((n) => `<li><i class="lin" style="background:var(--vv-r${n});height:${[2, 3, 4, 5, 6][n]}px"></i>`
      + `${NIVELES_RIESGO[n]} <span class="sub">${['menos de 20 %', '20–40 %', '40–60 %', '60–80 %', '80 % o más'][n]}</span></li>`).join('');
    return '<p class="ley-titulo">Riesgo de hueco por tramo</p><ul>' + filas
      + '<li><i class="pt" style="--c:var(--vv-punto-ref)"></i>Hueco (referencia)</li></ul>'
      + (corrida ? `<p class="sub">Modelo ${corrida.modelo} · ${corrida.version} · ${fechaDia(corrida.fecha)}</p>` : '');
  }
  const fila = (e, relleno) => `<li><i class="pt${relleno ? '' : ' anillo'}" style="--c:var(--vv-${e})"></i>`
    + `${ESTADO[e].nombre} <span class="sub">${{detectado: 'sin verificar', verificado: 'confirmado en sitio',
      reparado: '', descartado: 'no era un hueco'}[e]}</span></li>`;
  return '<p class="ley-titulo">Estado del hueco</p><ul>' + fila('detectado', true) + fila('verificado', true)
    + fila('reparado', false) + fila('descartado', false) + '</ul>'
    + '<p class="sub">Lleno = abierto · anillo = cerrado</p>'
    + '<p class="sub ley-tam">Tamaño = severidad: <i class="pt t1"></i> baja <i class="pt t2"></i> media <i class="pt t3"></i> alta</p>';
}
