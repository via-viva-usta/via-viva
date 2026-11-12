# Diseño del tablero de VÍA VIVA (decisión y licencias)

Revisión hecha el **10-nov-2026** (versiones del registro npm y tamaños medidos con `gzip -9` sobre los archivos de
jsDelivr; no son cifras de los proyectos). Dos tableros con la misma estética:

1. **Tablero local** (PC o Pi, sin internet): FastAPI + HTML/JS propios (`viaviva/web/`), mapa con Leaflet si hay copia
   local y, si no, un mapa simple en `<canvas>`. Ya existe y está probado.
2. **Tablero en línea** (Netlify, lee de Supabase): página estática sin compilación, en `web/en_linea/`.

## Dirección visual elegida (11-nov)

Maquetas en `docs/diseno/` (`maqueta.html?d=a|b`, `direccion_a.png`, `direccion_b.png`). AC eligió **combinarlas**:

| Tema | Dónde | Rasgos |
|---|---|---|
| **A · Asfalto** (oscuro, `<html class="tema-a">`) | Campo, Marcar, Sync, Sesiones, Revisión, Dataset, Demo | Casi negro, un acento ámbar de señal vial, Space Grotesk + JetBrains Mono para cifras |
| **B · Cartografía** (claro, por defecto) | Tablero (Alcaldía/Tránsito), entrada, PDF | Papel cálido, titulares Instrument Serif, verde profundo |

Mismos componentes y variables CSS (`viaviva/web/estilo.css`); fuentes de Google Fonts (OFL) con respaldo del sistema
si no hay internet.

**Decisión del 11-nov (AC):** el sitio en línea (`web/en_linea/`: portada y `tablero.html`) **conserva la marca de Dany**
(PR #30: asfalto, blanco y amarillo de señal; Archivo Black + Inter). El tema B queda para el **tablero local** de la
Alcaldía, la entrada y los reportes PDF. El tema B que se aplicó a la página anterior sigue archivado en
`docs/archivo/en_linea_tema_b_codex_2026-11-11/` solo como referencia; no se restaura.

## Comparación (10-nov-2026)

| Librería | Versión (fecha) | Licencia | ~min+gzip | Sin build | Nota |
|---|---|---|---|---|---|
| **MapLibre GL JS** | 6.17.0 (07-nov-2026) | BSD-3 | 295 KB + worker 147 KB | Sí (módulo ES) | Teselas vectoriales, ~6 000 líneas sin problema, `feature-state` para resaltar |
| deck.gl | 9.4.1 (28-oct-2026) | MIT | 576 KB | Sí | Más de lo necesario |
| Leaflet | 1.9.4 (may-2023) | BSD-2 | 42 KB | Sí | Raster; vectorial solo con plugin (se usa en el tablero local) |
| Apache ECharts | 6.1.0 (19-may-2026) | Apache-2.0 | 368 KB | Sí | Tema oscuro y `aria` incluidos; alternativa si se pide más accesibilidad en gráficos |
| **Chart.js** | 4.6.1 (22-oct-2026) | MIT | 71 KB | Sí | 5 veces más liviano que ECharts; necesita `aria-label` + tabla alternativa |
| Tremor | 3.18.7 (ene-2025) | Apache-2.0 | — | No (React + Tailwind) | Paquete estancado |
| shadcn/ui | CLI 4.23.0 | MIT | — | No (React) | Se copian componentes; requiere build |
| Mantine | 9.8.0 | MIT | — | No (React) | Requiere build |
| Tabler | 1.7.4 | MIT | 85 + 43 KB | Sí | Pesado para lo que se usa |
| Kepler.gl | 3.3.0-alpha.20 | MIT | muy grande | No | Herramienta de análisis, no tablero propio |
| **Pico.css** | 2.1.1 (mar-2025) | MIT | 11,6 KB | Sí | Claro/oscuro automático, buen contraste sin clases |
| **supabase-js** | 2.119.0 (04-nov-2026) | MIT | 56 KB | Sí | Autenticación y lectura con RLS |

**Decisión:** MapLibre GL JS + Chart.js + Pico.css + supabase-js, todo como módulos ES desde jsDelivr con versión fija.
Sin compilación: el equipo lo edita a mano. Un solo color de acento (azul `#1f6feb`), tipografía del sistema, tarjetas de
indicadores grandes, animaciones solo de transición (respetando `prefers-reduced-motion`), modo kiosco con `?kiosco=1`.

```
https://cdn.jsdelivr.net/npm/maplibre-gl@6.17.0/dist/maplibre-gl.mjs
https://cdn.jsdelivr.net/npm/maplibre-gl@6.17.0/dist/maplibre-gl.css
https://cdn.jsdelivr.net/npm/chart.js@4.6.1/auto/+esm
https://cdn.jsdelivr.net/npm/@picocss/pico@2.1.1/css/pico.min.css
https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.119.0/+esm
```

## Portada y marca (10-nov, rama `web/interfaz-dany`)

- **Portada** (`web/en_linea/index.html`) antes del tablero, para que los datos no aparezcan de golpe: qué hace VÍA VIVA,
  las tres preguntas que responde el tablero (con capturas DEMO marcadas), cómo leer el mapa, la base (cifras de OSM y
  datos abiertos, no resultados) y privacidad. No carga mapas, gráficos ni Supabase.
- **Marca** (`marca.css`), tomada de un sitio de estilo brutalista: asfalto `#0a0a0a`, blanco, gris `#9a9a9a`, amarillo de
  señal `#ffd60a` (acento de la portada y franja DEMO) y rojo `#ff3b30` (hueco en la portada). Titulares en **Archivo
  Black** (la referencia se ve en Arial Black, que no existe en Android) y texto en **Inter**, ambas OFL y **alojadas en el
  sitio** (`fuentes/`): la CSP no permite Google Fonts y así ningún tercero ve las visitas. Esquinas rectas, líneas finas.
- **Tablero:** oscuro por defecto (el botón ◐ cambia a claro y se recuerda); los controles usan blanco/negro y no colores
  de datos; filtros secundarios y leyenda plegados; lista de 15 en 15 (8 en el celular); cifras que cuentan y paneles
  que entran por partes (desactivado con `prefers-reduced-motion`).

## Mapa base

| Proveedor | Clave | Límites | Atribución | Claro / oscuro |
|---|---|---|---|---|
| **OpenFreeMap** | No | Sin límite de vistas; sin SLA (puede cerrarse sin aviso) | Obligatoria (MapLibre la pone) | Positron / Dark |
| CARTO | Sí (gratis) | No comercial: 5 M teselas/mes | © OpenStreetMap, © CARTO | Positron / Dark Matter |
| Stadia | Cuenta (por dominio) | 200 000 créditos/mes; académico permitido | Obligatoria | Alidade Smooth / Dark |
| MapTiler | Sí | 5 000 sesiones / 100 000 peticiones al mes | Logo obligatorio | Sí |
| OSM estándar | No | Solo raster, capacidad donada, prohíbe precargar | Obligatoria | Sin oscuro |

**Decisión:** OpenFreeMap (`https://tiles.openfreemap.org/styles/positron` y `/styles/dark`; el estilo Dark está marcado
"sin terminar" por su autor) con **CARTO como respaldo** (clave gratuita restringida al dominio, en la configuración pública
del sitio, nunca una clave secreta). Siempre se muestra la atribución © OpenStreetMap.

## Supabase y publicación

- **Supabase gratis:** 500 MB de base, 50 000 usuarios activos/mes, 5 GB de salida; el proyecto **se pausa tras una semana
  con poca actividad** (se restaura desde el panel). La Pi sincroniza a diario y eso suele bastar, sin garantía.
- **Netlify** (más simple: arrastrar la carpeta en Netlify Drop o enlazar el repo, sin build). Vercel Hobby también sirve,
  limitado a uso no comercial.
- La URL de Supabase y la **clave pública (anon)** van en `web/en_linea/config.js` (son públicas por diseño). La clave de
  servicio **nunca** va en la página: solo en el `.env` de la Pi para la sincronización.

## Principios aplicados

Modo claro y oscuro · un acento · mucho espacio en blanco · tarjetas grandes · contraste AA · todo usable con teclado
(foco visible) · adaptable a celular, portátil y pantalla fija de la Alcaldía · sin datos personales en pantalla.
