# Estado de VÍA VIVA

Última actualización: **2-nov-2026 (noche)**. Entrega final: **13-nov-2026**.
Tareas con responsable y fecha: *Issues* de GitHub (`via-viva-usta/via-viva`). Flujo de trabajo: `CONTRIBUTING.md`.

## Fases

| # | Fase | Fechas | Estado |
|---|---|---|---|
| 1 | Repositorio, datos y modelado (BD, OSM, scraping, diagramas) | 26–30 oct | ✅ Hecha |
| 2 | Firmware sin hardware, bot, mapa web, tablero | 28 oct – 2 nov | ✅ Hecha (compila; sin probar en placa) |
| 3 | Hardware y recorridos (montaje, pruebas por sensor, phyphox, E1–E4) | 2–6 nov | 🟡 Software listo; **falta el hardware y los recorridos** |
| 4 | Modelos: detector int8 en el nodo y modelo de riesgo | 3–8 nov | 🟡 Cadenas listas y probadas con datos sintéticos; faltan datos reales |
| 5 | Validación en campo (top-10 de riesgo vs. 10 al azar) | 6–9 nov | ⬜ Pendiente (depende de 3 y 4) |
| 6 | Entrega: tablero y mapa con datos reales, informe, póster, video, pitch | 9–13 nov | 🟡 Informe, guiones y póster escritos con marcas [PENDIENTE] |

Decisiones vigentes: `CLAUDE.md` (sección 1). Si la Alcaldía no entrega datos antes del **9-nov**, el modelo de riesgo se
entrena con los tramos revisados en recorridos + los reportes del bot (plan B, ya implementado: `--fuente auto`).

## Hecho

| Área | Qué | Dónde |
|---|---|---|
| A | Firmware para **ESP32 normal** (WROOM-32): ADXL345 FIFO + DMA ping-pong (VSPI), microSD por HSPI en la matriz GPIO, MPU-6050, VL53L0X, GPS, botón, LED | `firmware/nodo-sensores/` |
| A | **Detector por umbrales** y **maniobras** (giro izq./der., frenada) — ajustes del docente; igual en C y Python | `src/detector_umbral.h`, `src/maniobras.h`, `analysis/detector_umbral.py` |
| A | **Página web del nodo** (punto de acceso): último evento, velocidad, sensores, botones Hueco/Resalto/Otro | `src/servidor_web.cpp` |
| A | **Experimentos E1–E4** + memoria en la microSD; análisis y tablas para el informe | `src/experimentos.cpp`, `analysis/experimentos.py`, `docs/experimentos.md` |
| A | **Pruebas por sensor** (7 programas con PASA/FALLA) y **guía de montaje** | `firmware/nodo-sensores/pruebas/`, `docs/montaje.md` |
| A | Wokwi (ESP32, MPU-6050, microSD, botón, LED) | `firmware/nodo-sensores/wokwi/` |
| A | ESP32-CAM: PING/FOTO, difuminado total, programación con CP2102 | `firmware/nodo-camara/` |
| B | **Cadena de entrenamiento en un comando**: ventanas → características → bosque (emlearn) y red 1D int8 → C; LODO y comparación con el umbral | `analysis/entrenar_detector.py`, `analysis/modelo_cnn.py` |
| B | Notebook de phyphox (espectro, características, clasificador) y **protocolo de recorridos** para Pipe | `analysis/` |
| C | Base SQLite (8 tablas), **capa de acceso** `db/acceso.py`, **reconstrucción desde cero** probada | `db/` |
| C | ETL: grafo de Tunja (5 775 tramos), barrios (154), pendiente, lluvia IDEAM, noticias | `etl/` |
| C | **Recorridos → map-matching → tramos revisados** y eventos | `etl/recorridos.py` |
| C | Modelo de riesgo con validación por barrios y **plan B** (registra la fuente de las etiquetas) | `risk_model/` |
| C | **Bot de Telegram** (foto + ubicación + tipo, número de reporte, estado) | `bot/` |
| C | **Mapa web estático** (Leaflet) y tablero Java (hash, heap, BFS) | `web/`, `dashboard-java/` |
| D | Informe IEEE final con figuras desde el repo, guion de demo/video, contenido del póster | `report/`, `docs/demo.md`, `docs/poster.md` |
| D | Organización: issues por área con responsable y fecha, hitos por fase, `CONTRIBUTING.md` | GitHub, raíz |

## Probado y no probado

| Pieza | Probado | NO probado |
|---|---|---|
| Firmware nodo (3 entornos), pruebas por sensor (7), cámara | **Compilan** | **Nada en hardware** (la placa llega esta semana) |
| Wokwi | `sketch.ino` compila; `diagram.json` válido | La simulación |
| Detector por umbrales y maniobras | En Python con datos sintéticos | En C en la placa; calibración con recorridos reales |
| Base de datos | Reconstrucción completa desde una copia limpia (305 s) | PostgreSQL/PostGIS (solo preparado) |
| ETL OSM / IDEAM / barrios / elevación | Corrida real contra las fuentes | — |
| Recorridos y map-matching | Con recorridos **sintéticos** sobre calles reales (26/28 tramos con hueco recuperados) | Con un export real de phyphox |
| Cadena del detector | Completa con datos **sintéticos** (LODO, int8 = float32 en 100 % de las ventanas) | Con recorridos reales; los modelos del firmware hoy son **sintéticos** |
| Experimentos E1–E4 | El lector de `exp_*.csv` con un archivo de **ejemplo inventado** | Ninguna medición real |
| Modelo de riesgo (plan B) | De punta a punta en una base temporal con datos sintéticos | Con etiquetas reales (hoy 0) |
| Bot | Lógica con base temporal; app con token falso | Con Telegram real (falta pegar el token en `.env`) |
| Mapa web | En navegador con base de prueba | Publicado (no se publica todavía) |
| Tablero Java | Compila con Ant; pruebas de estructuras | Abrirlo en el IDE NetBeans; uso con el ratón |
| Informe LaTeX | **Compila** con MiKTeX 25.12: 4 páginas, sin errores ni referencias sin resolver | Con los resultados reales (19 marcas [PENDIENTE]) |

## Falta (en orden)

1. Montar el hardware con `docs/montaje.md` y correr las 7 pruebas (issue #1).
2. Recorridos con phyphox etiquetados (issue #5) → `etl.recorridos` y `entrenar_detector.py` con datos reales.
3. Firmware completo en la placa y E1–E4 + corriente (issues #2, #4).
4. Volver a entrenar el detector con datos reales y regenerar `modelo_cnn.h` / `modelo_bosque.h` (issue #7).
5. Modelo de riesgo con datos reales y validación en campo (issues #9, #10).
6. Token del bot y prueba con celulares (issue #8).
7. Llenar las 19 marcas `[PENDIENTE]` del informe con resultados reales (issue #13); ya compila con MiKTeX.

## Fuentes externas y licencias

| Fuente | Qué se usa | Licencia / condiciones |
|---|---|---|
| OpenStreetMap (vía osmnx / Overpass) | Grafo de calles, superficie, tipo de vía; teselas del mapa web | ODbL 1.0 — atribución "© OpenStreetMap contributors"; política de uso de teselas y de Overpass |
| IDEAM — datos.gov.co `s54a-sgyg` | Precipitación (datos crudos) | CC BY-SA 4.0 (IDEAM) |
| Alcaldía de Tunja — datos.gov.co `4ryc-k7fx` | Barrios y veredas (punto y sector) | CC BY-SA 4.0 (Alcaldía de Tunja). Dato abierto: distinto de los datos pedidos por oficio |
| OpenTopoData (SRTM 30 m) | Elevación de los nodos | SRTM: dominio público (NASA/USGS); API pública con límites de uso |
| Gobernación de Boyacá (RSS) | Títulos y enlaces de noticias | Contenido © Gobernación; solo título, resumen y enlace, citando la fuente |
| Datos pedidos a la Alcaldía / Tránsito (si llegan) | Inventario de huecos, siniestros | **No se publican** sin permiso (`data/alcaldia/`, ignorada) |
| Leaflet 1.9.4 | Mapa web | BSD-2-Clause |
| sqlite-jdbc 3.47.1.0 | Tablero Java | Apache 2.0 |
| python-telegram-bot 22 | Bot | LGPL-3.0 |
| PyTorch, scikit-learn, emlearn | Entrenamiento y exportación del detector | BSD-3 / BSD-3 / MIT |
| TinyGPSPlus, VL53L0X (Pololu) | Firmware | LGPL-2.1 / licencia de Pololu (ver cada librería) |
