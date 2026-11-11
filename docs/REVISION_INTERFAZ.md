# Revisión de la interfaz y de la consistencia de datos (10-nov-2026, rama `web/interfaz-dany`)

Revisión del tablero en línea (`web/en_linea/`), del tablero local (`viaviva/web/`), del mapa ciudadano (`web/`) y de
los datos que los alimentan. Cada hallazgo dice **dónde** está, **qué** pasa y si quedó **corregido en esta rama**,
**propuesto** o si es una **decisión de Andrés**. Lo corregido se verificó como se indica; lo que no se pudo probar
está en la última sección.

## 1. Hallazgos corregidos en esta rama

| # | Dónde | Qué pasaba | Cómo quedó |
|---|---|---|---|
| 1 | `web/en_linea/app.js` (lectura de Supabase) | Supabase devuelve **máximo 1 000 filas** por consulta. Con 5 775 tramos, el riesgo se cortaba en silencio: el top-10 y la cifra de tramos críticos salían de una muestra incompleta (y `limit(5000)` de huecos tampoco pasaba de 1 000) | `carga.js: leerTodo` pide página por página hasta una página vacía. **Sin probar contra Supabase real** (no hay proyecto creado) |
| 2 | `viaviva/almacen.py: peligros` (tablero local, pestaña Atención) | A cada hueco se le ponía `severidad = None`: la prioridad salía solo de la clase y **todos los huecos tenían nivel 3**, aunque la base ya guarda su severidad (baja/media/alta) | Usa la severidad del hueco. Prueba nueva `test_prioridad_de_atencion_usa_la_severidad_medida_del_hueco` (falla sin la corrección, pasa con ella) |
| 3 | Importar reparaciones (en línea) | El número del hueco (`id_local`) solo es único **dentro de cada equipo** (`pi-01`, `phyphox-pc`…). Con dos #12, el CSV cambiaba el primero que encontrara | Si el número se repite, se pide la columna `instancia`; en pantalla, `#12 (pi-01)`. Pruebas con Node |
| 4 | CSV descargado vs. importación | El CSV salía con `id_local` y la importación pide `id_hueco`: no se podía reutilizar. Las comillas salían con `JSON.stringify` (`\"`, que no es CSV) y la importación partía las notas que tenían comas | Columna `id_hueco`; CSV estándar (RFC 4180) al escribir y al leer, con `,` o `;` |
| 5 | Fechas | El filtro «Desde» se leía en UTC (corría 5 h: un hueco del 31-oct a las 8 p. m. entraba en el 1-nov) y «Hasta» en hora local. El gráfico semanal agrupaba en UTC y **omitía las semanas sin datos** (la línea unía puntos lejanos) | Todo en hora de Tunja; semanas sin datos valen 0. Pruebas con Node del caso domingo 9 p. m. |
| 6 | Mapa en línea | Al cambiar claro/oscuro se registraban otra vez los clics del mapa: un clic abría el detalle 2, 3… veces | Los eventos se registran una sola vez |
| 7 | Colores del mapa | El rojo de «riesgo 60–80 %» era **el mismo** que el de «hueco detectado» (`#d6402b`) y el ámbar de «verificado» se confundía con el naranja del riesgo: los huecos se perdían sobre las calles. Además se pintaban los 5 775 tramos, también los de riesgo bajo | Dos modos: **Huecos** (calles sin color, puntos por estado: lleno = abierto, anillo = cerrado) y **Riesgo** (calles por nivel; lo muy bajo casi no se ve; huecos como puntos oscuros de referencia) |
| 8 | Indicador «en vivo» | Punto verde que latía siempre, aunque la Pi llevara días sin sincronizar | «Último dato: fecha y hora», en ámbar si tiene más de 2 días |
| 9 | Cifras y filtros | Las cifras no cambiaban con los filtros; un gráfico sí y el otro no | Una regla: severidad, tipo y periodo filtran todo; Abiertos/Reparados/Todos filtran mapa y lista. Una línea dice qué se está viendo |
| 10 | Palabras | «Baches» en el tablero en línea y «huecos» en la base, el tablero local y los documentos; `impacto_fuerte`, `residential`, `primary` y «tramo 128653127» en pantalla | «Huecos» en todo; «Golpe sin clasificar»; tipos de vía en español; un tramo sin nombre se describe por la calle con nombre que lo toca («Sin nombre, junto a Calle 2 y Carrera 5») |
| 11 | Lista y accesibilidad | No había lista de huecos (solo clic en el mapa) y los gráficos no tenían tabla alternativa, aunque `docs/DISENO.md` la pedía | Pestaña «Para atender» ordenada por prioridad, detalle en el panel (el mapa sigue a la vista), «Ver los números» bajo el gráfico, foco visible, flechas en grupos y pestañas |
| 12 | Menú Exportar | Se abría fuera de la pantalla por la derecha | Alineado a la derecha |
| 13 | Datos DEMO | El tope de 0,97 hacía que el top-10 entero empatara en 97 % | Riesgo sin tope y huecos más frecuentes en tramos de más riesgo (sigue siendo DEMO, con aviso) |
| 14 | `tramos_demo.py` (raíz, sin seguimiento) | Bajaba vías de OSM con **ids de vía OSM**, no `id_tramo` de la base (que sale de osmnx, una cuadra por tramo): publicado en Netlify, el riesgo y los huecos reales no se habrían ubicado | Movido a `herramientas/tramos_demo.py`; el archivo queda marcado `"demo": true` y la página avisa si se usa sin `?demo=1` |

## 2. Hallazgos propuestos (no se tocaron)

| # | Dónde | Qué pasa | Propuesta | Quién decide |
|---|---|---|---|---|
| A | `viaviva/sincronizacion.py: traer_cambios` + `supabase_esquema.sql` | Una reparación importada **en línea** guarda la fecha real solo en la nota; la Pi pone como fecha el momento en que sincroniza. En la importación **local** sí se usa la fecha real. Así, el tiempo de reparación de lo importado en línea sale más largo de lo real. Tampoco se lee `origen` (csv/web) | Columna `fecha` en `cambios_remotos` y pasarla como `ts=` a `cambiar_estado_hueco` | Andrés (cambia el esquema de Supabase) |
| B | `viaviva/web/tablero.html` | La casilla «Simulados» viene **marcada**: las cifras de la Alcaldía mezclan DEMO/reproducciones con datos reales | Desmarcada por defecto | Andrés |
| C | Tres pantallas | Riesgo con cortes fijos 20/40/60/80 en los dos tableros, pero por **quintiles** en el mapa ciudadano (`web/index.html`): el mismo tramo sale de colores distintos. Tres nombres para el mismo número: «Riesgo», «Prob.» y «Riesgo de hueco no reportado» | Una sola escala y un solo nombre (`web/en_linea/reglas.js: CORTES_RIESGO`) | Andrés |
| D | `web/index.html` (mapa ciudadano) | Dice «en tiempo real» pero es un `datos.js` fijo; muestra **eventos crudos** (un hueco reparado sigue apareciendo para siempre); la capa de reportes está vacía (bot pospuesto); los nombres de OSM van a `bindPopup` sin escapar | Mostrar huecos abiertos con su estado, fecha de los datos en vez de «tiempo real», quitar la capa vacía, escapar textos | Equipo |
| E | Vocabularios | Estados distintos para huecos (detectado → verificado → reparado/descartado) y reportes (nuevo → confirmado → en_reparacion → reparado/descartado); severidad `baja/media/alta` (sensor) vs. `leve/media/alta` (fotos); tres listas de clases (detector, marcas 1–7, fotos 9) | Una tabla de equivalencias en `docs/DATOS.md` y, donde se muestren juntos, un solo nombre | Andrés |
| F | `viaviva/web/tablero.html` | La cifra «Tramos con riesgo» cuenta todos los tramos con valor (≈ 5 775): no informa nada | «Tramos con riesgo alto (≥ 60 %)», como en línea | Equipo |
| G | `viaviva/web/` vs. `web/en_linea/` | Los dos tableros reimplementan filtros, leyenda, prioridad e importación, y ya divergieron (hallazgos 2, 7, 9, F) | Que `tablero.html` use `reglas.js` (servido en `/static`) para un solo vocabulario | Equipo, después del 13-nov |
| H | `viaviva/web/comun.js` | El tablero local usa teselas de `tile.openstreetmap.org`; su política no permite el uso intensivo (una pantalla fija 24/7) | OpenFreeMap, como en línea (`docs/DISENO.md`) | Equipo |
| I | `riesgo.rango` | «Rango» es en realidad el **puesto** (1 = más riesgo) | Documentarlo o renombrarlo a `puesto` | Andrés |

## 3. Documentos desactualizados

- `docs/ESTADO.md`: dice «Última actualización: 7-nov»; las tareas de Dany siguen siendo de la ESP32 (#1, #2, #4, #18)
  y los bloqueos hablan del hardware de la ESP32, que salió del proyecto el 9-nov.
- `CLAUDE.md`, `docs/ESTADO.md` y `docs/cambios_informe.md`: 11 líneas con rutas `pi/…` (la carpeta ahora es `viaviva/`).
- `db/schema.sql`: no tiene `huecos.severidad` (solo llega por la migración de `db/acceso.py`). Funciona, pero el
  esquema no lo muestra.
- `docs/README.md` no listaba los documentos del 10-nov (corregido en esta rama).
- Permisos: según #17, `dany286-ri` tiene **read** en el repositorio; para subir esta rama hace falta **Write**.

## 4. Cómo quedó el tablero en línea

```
Barra: VÍA VIVA · «Último dato: 10 nov, 2:32 p. m.» · ? (cómo leer) · claro/oscuro · Pantalla fija · cuenta
Cifras (también son atajos): Huecos abiertos · Abiertos de severidad alta · Reparados · Tramos con riesgo alto
Filtros: [Abiertos | Reparados | Todos] · Severidad · Tipo · Periodo (7/30/90 días o fechas) · Quitar filtros · Descargar
«En el mapa: 106 huecos abiertos · últimos 30 días.»
Mapa [Huecos | Riesgo por tramo] + leyenda en palabras  │  Panel: Para atender · Tramos en riesgo · Tendencia
```

- **Para atender:** huecos ordenados por prioridad (severidad × tipo de vía × huecos abiertos en el tramo, la misma
  fórmula del tablero local), con la razón a la vista («severidad alta», «vía principal», «2 abiertos en el tramo») y
  cuánto lleva abierto. Al tocar uno, el mapa vuela hasta él y el detalle se abre en el panel: pasos del estado, datos
  en palabras, prioridad explicada y «Cómo llegar».
- **Tramos en riesgo:** top-10 con barra, nivel en palabras y huecos abiertos del tramo; explica qué significa el
  porcentaje y marca la corrida DEMO.
- **Tendencia:** huecos nuevos vs. reparados por semana (si lo naranja supera a lo verde, aparecen más de los que se
  reparan), tabla con los números y calles o barrios con más huecos abiertos.
- **Celular:** filtros plegados, leyenda cerrada, lista de 8 en 8; un dedo desplaza la página y dos mueven el mapa.
- **Imprimir (PDF):** cifras, qué se está viendo, mapa, leyenda y los 15 primeros.
- **Código:** `reglas.js` (vocabulario y fórmulas, sin dependencias), `carga.js` (Supabase, DEMO y preparación),
  `mapa.js` (MapLibre), `app.js` (pantalla), `tema.js` (claro/oscuro antes de pintar; la CSP no permite scripts en línea).
  Misma pila de `docs/DISENO.md` (MapLibre + Chart.js + Pico + supabase-js, sin compilación).

## 4b. Portada y menos saturación (segunda ronda, 10-nov)

Pedido: una portada para que los datos no aparezcan de golpe, una página más bonita y menos datos a la vez. Referencia
de diseño: un sitio de estilo brutalista (asfalto, titulares enormes, columnas con líneas finas, tarjetas blancas).

| Antes | Ahora | Por qué |
|---|---|---|
| Se entraba directo al tablero | `index.html` = portada (qué hace, el tablero en 3 preguntas, cómo leer el mapa, la base, privacidad); el tablero pasa a `tablero.html` | Quien llega por primera vez entiende qué mira antes de ver 100 puntos |
| Todo aparecía de una vez | Cifras que cuentan desde 0; cifras, filtros, mapa y panel entran escalonados; los puntos del mapa con fundido; la lista entra fila por fila al cambiar filtros | «Que no aparezcan de golpe» (sin animación si el sistema pide menos movimiento) |
| 7 controles de filtro a la vista | Solo Abiertos/Reparados/Todos; el resto detrás de «Filtros»; los filtros activos se ven como chips con ✕ | Menos decisiones a la vez |
| Filas con 3–4 cajitas y número + estado | Una línea: severidad · tipo de vía · «2 en el tramo» · barrio; el estado lo dice el color del círculo (y un texto para lectores de pantalla) | Leer de un vistazo |
| 60 filas en la lista | 15 (8 en el celular) y «Mostrar más» | Evitar el muro de datos |
| Leyenda abierta (6 líneas sobre el mapa) | Una línea («● Detectado ● Verificado ○ Reparado»); se abre para el detalle | El mapa se ve |
| Aviso DEMO rojo de un renglón grueso | Franja amarilla de precaución bajo la barra | Igual de visible, menos alarmante |
| Azul de Pico y bordes redondeados | Marca de VÍA VIVA (oscuro por defecto, claro con ◐), Archivo Black + Inter locales | Identidad y coherencia con la portada |

Verificado con la **CSP real** de `netlify.toml` (servidor de prueba con las mismas cabeceras): fuentes, imágenes, estilos,
el *worker* del mapa y los gráficos cargan sin bloqueos. Las imágenes de la portada (`img/*.webp`, 45–95 KB) salen del
tablero en modo DEMO y llevan el sello «Datos de demostración».

## 5. Cómo probarlo sin la base (por ejemplo, en un Mac)

```
python3 herramientas/tramos_demo.py            # una vez: calles DEMO en web/en_linea/datos/ (ignorado por Git)
cd web/en_linea && python3 -m http.server 8765
```

- `http://127.0.0.1:8765/` — la portada.
- `http://127.0.0.1:8765/tablero.html?demo=1` — datos inventados, con aviso.
- `…/tablero.html?demo=1&rol=editor` — también los controles de edición e importación (en DEMO no se envía nada).
- `…/tablero.html?demo=1&kiosco=1` — pantalla fija (Esc para salir).

## 6. Qué se verificó y qué no

- **Verificado:** 13 escenarios en Chrome sin pantalla (escritorio 1440 px claro y oscuro, detalle, riesgo, tendencia,
  editor, importación con un CSV con errores, celular 390 px, filtros y «Mostrar más» en el celular, pantalla fija
  1920 px, imprimir, sin `config.js`): sin errores de consola y sin desborde horizontal. 6 pruebas de Node para
  `reglas.js` (prioridad, niveles, nombres, fechas, CSV, importación) y `pytest tests/test_viaviva.py` (19 pasan,
  1 omitida; la de `pandas` no se corrió en este Mac), `ruff` limpio.
- **No verificado:** contra un Supabase real (no hay proyecto), en un iPhone/Safari real, ni con datos reales (no hay
  huecos sincronizados todavía). La advertencia «wood-pattern» de la consola viene del estilo oscuro de OpenFreeMap
  (marcado «sin terminar» por su autor), no del tablero.
