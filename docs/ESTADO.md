# Estado de VÍA VIVA

Última actualización: **3-nov-2026**. Entrega final: **13-nov-2026**. Decisiones y datos técnicos: `CLAUDE.md`.
Tareas: issues de GitHub (`via-viva-usta/via-viva`, 17 creados, 16 abiertos). Flujo de trabajo: `CONTRIBUTING.md`.

## Resumen en 5 líneas

1. **Todo el software existe y compila o corre**, pero **nada se ha probado en hardware** (la placa llega esta semana).
2. **No hay ningún dato real de recorridos todavía**: detector, entrenamiento y modelo de riesgo se probaron solo con datos
   **sintéticos** (marcados) y no tienen resultados.
3. La base real tiene el grafo de Tunja, barrios, pendiente y lluvia; **0 eventos, 0 reportes, 0 etiquetas, 0 corridas de riesgo**.
4. El informe compila (MiKTeX) con **19 marcas `[PENDIENTE]`** que solo se llenan con mediciones reales.
5. Lo que destraba todo: **montar el nodo (Dany) y los primeros recorridos con phyphox (Pipe)**.

## Fases

| # | Fase | Fechas | Estado |
|---|---|---|---|
| 1 | Repositorio, datos y modelado | 26–30 oct | ✅ Hecha |
| 2 | Firmware sin hardware, bot, mapa web, tablero | 28 oct – 2 nov | ✅ Hecha (compila; sin probar en placa) |
| 3 | Hardware y recorridos (montaje, pruebas por sensor, phyphox, E1–E4) | 2–6 nov | 🟡 Software listo; **falta hardware y recorridos** |
| 4 | Detector int8 y modelo de riesgo con datos reales | 3–8 nov | 🟡 Cadenas listas (probadas con sintéticos); faltan datos |
| 5 | Validación en campo (top-10 vs. 10 al azar) | 6–9 nov | ⬜ Depende de 3 y 4. **9-nov: si no hay datos de la Alcaldía → plan B** |
| 6 | Entrega: datos reales en tablero y mapa, informe, póster, video, pitch | 9–13 nov | 🟡 Informe, guiones y póster escritos con [PENDIENTE] |

## Hecho (y dónde está)

| Área | Qué | Dónde |
|---|---|---|
| A | Firmware **ESP32 normal**: ADXL345 FIFO (watermark 31) + DMA ping-pong por VSPI, microSD por HSPI en la matriz GPIO, MPU-6050, VL53L0X, GPS, botón, LED; tareas en 2 núcleos | `firmware/nodo-sensores/` |
| A | **Detector por umbrales** y **maniobras** (ajustes del docente), iguales en C y Python | `src/detector_umbral.h`, `src/maniobras.h`, `analysis/detector_umbral.py` |
| A | **Página web del nodo** (punto de acceso `VIA-VIVA-NODO`, botones Hueco/Resalto/Otro, modo mesa) | `src/servidor_web.cpp` |
| A | **E1–E4** + memoria a `exp_NNN.csv`; procedimiento y medición de corriente | `src/experimentos.cpp`, `docs/experimentos.md` |
| A | **7 programas de prueba por sensor** (PASA/FALLA) y **guía de montaje** | `firmware/nodo-sensores/pruebas/`, `docs/montaje.md` |
| A | Wokwi (ESP32, MPU-6050, microSD, botón, LED) | `firmware/nodo-sensores/wokwi/` |
| A | ESP32-CAM: PING/FOTO, difuminado total, programación con CP2102 | `firmware/nodo-camara/` |
| B | **Cadena de entrenamiento en un comando** (bosque emlearn + red 1D int8 → C; LODO; vs. umbral) | `analysis/entrenar_detector.py`, `analysis/modelo_cnn.py` |
| B | Notebook phyphox y **protocolo de recorridos** (con formato de `_etiquetas.csv`) | `analysis/` |
| B | Tablas y gráficas de E1–E4 para el informe | `analysis/experimentos.py` |
| C | Base SQLite (8 tablas), capa de acceso, **reconstrucción desde cero probada** | `db/` |
| C | ETL: OSM, barrios, elevación/pendiente, lluvia IDEAM, noticias (robots.txt) | `etl/` |
| C | **Recorridos → map-matching → tramos revisados** + generador de recorridos sintéticos | `etl/recorridos.py`, `etl/recorrido_sintetico.py` |
| C | Modelo de riesgo con validación por barrios y **plan B** (`--fuente`, fuente registrada) | `risk_model/` |
| C | **Bot de Telegram** (foto + ubicación + tipo → número de reporte; `/estado`) | `bot/` |
| C | **Mapa web estático** (Leaflet) y **tablero Java** (tabla hash, heap, BFS, geohash) | `web/`, `dashboard-java/` |
| D | **Informe IEEE** con figuras y cifras generadas desde la base; compila con MiKTeX | `report/` |
| D | Guion de demo y video, contenido del póster | `docs/demo.md`, `docs/poster.md` |
| D | GitHub: etiquetas por área, 6 hitos, 17 issues; `CONTRIBUTING.md` | GitHub |
| D | Paquete para Juan Diego: `.docx` (Introduction, Related Work, Methodology con notas de lo que falta), PDF del informe, póster y demo | `05_SOFTWARE\para_anzola\` (**fuera del repo**) |

## Probado y NO probado

| Pieza | Probado | NO probado |
|---|---|---|
| Firmware del nodo (3 entornos) | **Compila** (RAM 18,4 %, flash 46,6 %) | **Nada en la placa**: pines, FIFO/DMA, overruns, web, microSD, GPS |
| Pruebas por sensor (7) y ESP32-CAM | **Compilan** | En hardware |
| Wokwi | `sketch.ino` compila; `diagram.json` válido | La simulación |
| Detector por umbrales y maniobras | En Python con datos sintéticos | En C en la placa; **parámetros sin calibrar** |
| Base y ETL | Reconstrucción desde una copia limpia (305 s); corrida real contra OSM, IDEAM, datos abiertos y OpenTopoData | PostgreSQL/PostGIS (solo preparado) |
| Recorridos y map-matching | Con 3 recorridos **sintéticos** sobre calles reales: 26 de 28 tramos con hueco recuperados | Con un export **real** de phyphox (los nombres de columnas pueden variar) |
| Cadena del detector | Completa con 6 recorridos **sintéticos**; int8 = float32 en el 100 % de las ventanas | Con datos reales. **Los modelos del firmware son sintéticos** (`MODELO_SINTETICO 1`) |
| Experimentos E1–E4 | El lector, con un archivo de **ejemplo inventado** | **Ninguna medición real**; corriente sin medir |
| Modelo de riesgo (plan B) | De punta a punta en una base **temporal** con datos sintéticos (AUC ≈ 0,5, lo esperado) | Con etiquetas reales (hoy **0**) |
| Bot | Lógica con base temporal; app con token falso. **El token ya está en `.env`** (3-nov) | **Con Telegram real** (`/reportar` con celulares) |
| Mapa web | En navegador con base de prueba (aviso DEMO, capas, leyenda) | Publicado (no se publica hasta que el equipo apruebe) |
| Tablero Java | Compila con Ant; `PruebaEstructuras` pasa con la base real | Abrirlo en el **IDE** NetBeans; uso con el ratón |
| Informe | **Compila** con MiKTeX 25.12: 4 páginas, sin errores ni referencias sin resolver | Con resultados reales (19 `[PENDIENTE]`) |

## Cifras reales ya calculadas (se pueden usar)

| Cifra | Valor | Fuente |
|---|---|---|
| Grafo de Tunja | 4 054 nodos, 5 775 tramos, 537,6 km; superficie en OSM solo en 11 % | `etl.osm_tunja` (OSM puede variar levemente entre días) |
| Pendiente (SRTM 30 m) | 4 659 tramos ≥ 30 m; mediana 4,8 %, p90 13,7 % | `etl.elevacion` |
| Barrios | 154 (9 veredas, 11 sectores) | datos abiertos `4ryc-k7fx` |
| Lluvia | 5 estaciones IDEAM ≤ 15 km, diaria | `etl.scraping.clima_ideam` |
| Tablero | Búsqueda del tramo más cercano: 108 comparaciones (geohash) vs. 5 775 (fuerza bruta), mismo resultado en 2 000 búsquedas | `PruebaEstructuras` |
| Red 1D | 788 parámetros; 3 152 B float32 vs. 872 B int8 | `entrenar_detector.py` (independiente de los datos) |
| Reconstrucción de la base | 305 s desde cero | `db/reconstruir.ps1` |

## Qué falta, por persona

### Dany Cipamocha (área A) — issues #1, #2, #3, #4
1. **Montar el nodo** siguiendo `docs/montaje.md` y correr las **7 pruebas** de `firmware/nodo-sensores/pruebas/`; anotar PASA/FALLA en #1. *(4-nov)*
2. Subir el **firmware completo** (`pio run -t upload`): arranque con microSD, `overruns = 0`, página http://192.168.4.1, etiquetas en la microSD; confirmar el signo del giro del MPU (#2). *(5-nov)*
3. **ESP32-CAM** con el CP2102 y prueba PING/FOTO (#3). *(5-nov)*
4. **E1–E4 y corriente** con el tester USB según `docs/experimentos.md`; copiar `exp_*.csv` a `data/raw/nodo/` (#4). *(6-nov)*
5. Necesita **permiso de escritura** en el repo para trabajar con PR (lo da Andrés, #17).

### Juan Felipe García — Pipe (área B) — issues #5, #6, #7
1. **≥ 3 recorridos con phyphox** (acelerómetro con g + giroscopio + GPS, ≤ 30 km/h, celular fijo) con su `_etiquetas.csv`, según `analysis/README.md`; dejarlos en la carpeta compartida → `data/raw/phyphox/` (#5). *(4-nov)*
2. Con esos datos: **espectro y fs** (notebook) y **calibrar el detector por umbrales** (#6). *(5-nov)*
3. Correr `analysis/entrenar_detector.py` con datos reales y **regenerar `modelo_cnn.h` / `modelo_bosque.h`** (#7). *(7-nov)*
4. No está en la organización de GitHub: Andrés debe invitarlo (#17).

### Andrés Cárdenas (áreas C y D) — issues #8–#13, #15, #17
1. **Ya**: dar Write a `dany286-ri`, invitar a Pipe y confirmar si `Juandi-1` es Juan Diego (#17).
2. **Probar el bot con celulares** (el token ya está en `.env`): `bot\.venv\Scripts\python bot\bot.py` (#8). *(3-nov)*
3. Con los recorridos: `python -m etl.recorridos` → `risk_model.variables` → `risk_model.modelo --fuente auto --guardar --lista-campo` (#9). *(8-nov)*
4. **Validación en campo**: visitar los 20 tramos de la lista y guardar el resultado como `data/campo/tramos_revisados_visita_<fecha>.csv` (#10). *(9-nov)*
5. Seguir los oficios a la Alcaldía/Tránsito; **9-nov decide plan B** (#12).
6. Tablero en el IDE NetBeans, `web/exportar.py` con datos reales y publicar en Netlify cuando el equipo apruebe (#11). *(11-nov)*
7. Llenar los `[PENDIENTE]` del informe y recompilar (#13). *(12-nov)*
8. Antes de hacer público el repo: correos y nombres en `docs/propuesta/` y `docs/03_...` (#15). *(13-nov)*

### Juan Diego Anzola (apoyo A y D) — issue #14
1. Revisar el `.docx` de `para_anzola` (Introduction, Related Work, Methodology): las notas en ámbar dicen qué falta
   (trabajos de predicción de deterioro vial y de reporte ciudadano; procedimiento de recolección en campo; ESP32-CAM).
2. **Póster, video de respaldo (< 5 min) y pitch** con `docs/poster.md` y `docs/demo.md` (#14). *(12-nov)*
3. Apoyar a Dany en el montaje y las mediciones.

## Estado local del PC de Andrés (no está en Git)

- `data/via_viva.db`: reconstruida el 2-nov; tablas de contexto llenas, **sin eventos, reportes, etiquetas ni corridas de riesgo**
  (el tablero y el mapa muestran todos los tramos en gris).
- `data/raw/phyphox_sintetico/` y `data/campo/sintetico/`: datos **sintéticos** de prueba; `data/campo/visita_2026-10-26_DEMO.csv`
  es de la demo vieja (se puede borrar).
- `.env`: con `TELEGRAM_BOT_TOKEN` (pegado por Andrés) y `BOT_SAL_HASH` (no cambiarla: los hashes dejarían de coincidir).
- `05_SOFTWARE\para_anzola\`: paquete para Juan Diego (`.docx`, PDF, `poster.md`, `demo.md`).
- MiKTeX instalado por usuario; PlatformIO en `%USERPROFILE%\.platformio`; venvs `etl\.venv`, `analysis\.venv`, `bot\.venv`.

## Fuentes externas y licencias

| Fuente | Qué se usa | Licencia / condiciones |
|---|---|---|
| OpenStreetMap (osmnx / Overpass) | Grafo de calles; teselas del mapa web | ODbL 1.0 — "© OpenStreetMap contributors"; políticas de uso de teselas y Overpass |
| IDEAM — datos.gov.co `s54a-sgyg` | Precipitación (datos crudos) | CC BY-SA 4.0 |
| Alcaldía de Tunja — datos.gov.co `4ryc-k7fx` | Barrios y veredas (punto y sector) | CC BY-SA 4.0. Dato abierto: distinto de los datos pedidos por oficio |
| OpenTopoData (SRTM 30 m) | Elevación de los nodos | SRTM: dominio público (NASA/USGS); API con límites de uso |
| Gobernación de Boyacá (RSS) | Títulos y enlaces de noticias | Contenido © Gobernación; solo título, resumen y enlace |
| Datos pedidos a Alcaldía / Tránsito (si llegan) | Inventario de huecos, siniestros | **No se publican** sin permiso (`data/alcaldia/`, ignorada) |
| Leaflet 1.9.4 · sqlite-jdbc 3.47.1.0 · python-telegram-bot 22 | Mapa, tablero, bot | BSD-2 · Apache 2.0 · LGPL-3.0 |
| PyTorch · scikit-learn · emlearn | Entrenamiento y exportación del detector | BSD-3 · BSD-3 · MIT |
| TinyGPSPlus · VL53L0X (Pololu) | Firmware | LGPL-2.1 · licencia de Pololu |
