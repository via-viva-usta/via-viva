// VÍA VIVA · menú desplegable compartido por la portada (index.html) y el tablero (tablero.html).
// Una cuadrícula de opciones en dos grupos, cada una con un modelo 3D (Kenney, CC0: modelos/LEEME.md). El visor
// <model-viewer> (Google, Apache-2.0) se descarga SOLO la primera vez que se abre el menú: la portada sigue liviana.
// Accesible: botón con aria-expanded, Esc cierra y devuelve el foco, clic afuera cierra, sin giro si se pide menos movimiento.
const VISOR_3D = 'https://cdn.jsdelivr.net/npm/@google/model-viewer@4.4.0/dist/model-viewer.min.js';
const GRUPOS = [
  {nombre: 'Tablero', opciones: [
    {titulo: 'Huecos para atender', texto: 'La lista por prioridad: cuál arreglar primero y cuántos días lleva abierto.',
      href: 'tablero.html#atender', modelo: 'modelos/carreras/track-bump.glb', orbita: '20deg 62deg 105%'},
    {titulo: 'Riesgo por tramo', texto: 'Qué cuadras pueden tener un hueco que nadie ha reportado.',
      href: 'tablero.html#riesgo', modelo: 'modelos/ciudad/road-corner.glb', orbita: '35deg 58deg 105%'},
    {titulo: 'Tendencia', texto: 'Huecos nuevos contra reparados, semana a semana.',
      href: 'tablero.html#tendencia', modelo: 'modelos/carreras/vehicle-truck-yellow.glb', orbita: '35deg 70deg 105%'},
  ]},
  {nombre: 'Proyecto', opciones: [
    {titulo: 'Cómo funciona', texto: 'Del sensor a bordo del carro al mapa de la ciudad, en tres pasos.',
      href: 'index.html#como', modelo: 'modelos/carreras/vehicle-truck-red.glb', orbita: '-35deg 70deg 105%'},
    {titulo: 'Cómo leer el mapa', texto: 'Colores, tamaños y estados en cuatro reglas.',
      href: 'index.html#leer', modelo: 'modelos/ciudad/road-intersection.glb', orbita: '30deg 58deg 105%'},
    {titulo: 'Estado del prototipo', texto: 'Qué está listo y qué falta para enlazar los datos reales.',
      href: 'index.html#estado', modelo: 'modelos/ciudad/building-garage.glb', orbita: '35deg 66deg 105%'},
  ]},
];
const MAS = [['La base de calles', 'index.html#base'], ['Privacidad', 'index.html#privacidad'], ['Entrar (equipo)', 'tablero.html?entrar=1']];

const quieto = matchMedia('(prefers-reduced-motion: reduce)').matches;
const pagina = location.pathname.split('/').pop() || 'index.html';
/** Un enlace a la misma página se vuelve solo «#ancla»: cambia de sección sin recargar. */
const destino = (href) => {
  const [archivo, ancla] = href.split('#');
  return ancla && archivo === pagina ? '#' + ancla : href;
};

const boton = document.getElementById('b-menu');
if (boton) {
  const panel = document.createElement('nav');
  panel.id = 'menu-panel'; panel.className = 'menu-panel'; panel.hidden = true;
  panel.setAttribute('aria-label', 'Menú principal');
  let n = 0;
  panel.innerHTML = '<div class="menu-dentro">' + GRUPOS.map((g, gi) => `<section class="menu-grupo">
      <p class="t-etiqueta menu-grupo-nombre">${String(gi + 1).padStart(2, '0')} — ${g.nombre}</p>
      <ul class="menu-rejilla">${g.opciones.map((o) => `<li style="--i:${n++}"><a class="menu-op" href="${destino(o.href)}">
        <span class="menu-3d" data-modelo="${o.modelo}" data-orbita="${o.orbita}" aria-hidden="true"></span>
        <span class="menu-txt"><span class="menu-titulo">${o.titulo}</span><span class="menu-texto">${o.texto}</span></span>
        <span class="menu-ir" aria-hidden="true">→</span></a></li>`).join('')}</ul></section>`).join('')
    + `<div class="menu-pie"><nav aria-label="Más enlaces">${MAS.map(([t, h]) => `<a href="${destino(h)}">${t}</a>`).join('')}</nav>
      <button type="button" class="menu-cerrar">Cerrar <span aria-hidden="true">✕</span></button></div></div>`;
  const velo = Object.assign(document.createElement('div'), {className: 'menu-velo', hidden: true});
  document.body.append(velo, panel);
  boton.setAttribute('aria-controls', 'menu-panel'); boton.setAttribute('aria-expanded', 'false');

  let cargado = false;
  async function cargar3D() {
    if (cargado) return;
    cargado = true;
    try { await import(VISOR_3D); } catch (e) { panel.classList.add('sin-3d'); return; }   // sin internet: tarjetas sin 3D
    for (const c of panel.querySelectorAll('.menu-3d')) {
      const v = document.createElement('model-viewer');
      Object.entries({src: c.dataset.modelo, 'camera-orbit': c.dataset.orbita, 'interaction-prompt': 'none',
        'disable-zoom': '', 'disable-pan': '', 'disable-tap': '', 'shadow-intensity': '0.9', 'shadow-softness': '0.8',
        exposure: '1.05', 'environment-image': 'neutral', loading: 'eager', 'rotation-per-second': '14deg'})
        .forEach(([k, val]) => v.setAttribute(k, val));
      v.setAttribute('auto-rotate-delay', '0');
      c.append(v);
    }
  }
  const abierto = () => boton.getAttribute('aria-expanded') === 'true';
  // con el menú cerrado los modelos no giran (no gastan batería ni piden cuadros de animación ocultos)
  const girar = (si) => { if (!quieto) panel.querySelectorAll('model-viewer').forEach((v) => v.toggleAttribute('auto-rotate', si)); };
  function abrir() {
    const cab = boton.closest('header');
    panel.style.top = Math.max(0, cab ? cab.getBoundingClientRect().bottom : 0) + 'px';
    panel.hidden = false; velo.hidden = false;
    requestAnimationFrame(() => { panel.classList.add('abierto'); velo.classList.add('abierto'); });
    boton.setAttribute('aria-expanded', 'true');
    document.documentElement.classList.add('menu-abierto');
    cargar3D().then(() => girar(true));
    panel.querySelector('.menu-op')?.focus({preventScroll: true});
  }
  function cerrar(devolverFoco = true) {
    if (!abierto()) return;
    panel.classList.remove('abierto'); velo.classList.remove('abierto');
    girar(false);
    boton.setAttribute('aria-expanded', 'false');
    document.documentElement.classList.remove('menu-abierto');
    setTimeout(() => { if (!abierto()) { panel.hidden = true; velo.hidden = true; } }, quieto ? 0 : 260);
    if (devolverFoco) boton.focus({preventScroll: true});
  }
  boton.addEventListener('click', () => (abierto() ? cerrar() : abrir()));
  velo.addEventListener('click', () => cerrar());
  panel.querySelector('.menu-cerrar').addEventListener('click', () => cerrar());
  panel.addEventListener('click', (e) => { if (e.target.closest('a')) cerrar(false); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && abierto()) cerrar(); });
  // al pasar el mouse, el modelo gira más rápido (solo si el movimiento está permitido)
  if (!quieto) {
    panel.addEventListener('pointerover', (e) => {
      const v = e.target.closest('.menu-op')?.querySelector('model-viewer');
      if (v) v.setAttribute('rotation-per-second', '80deg');
    });
    panel.addEventListener('pointerout', (e) => {
      const op = e.target.closest('.menu-op');
      if (op && !op.contains(e.relatedTarget)) op.querySelector('model-viewer')?.setAttribute('rotation-per-second', '14deg');
    });
  }
}
