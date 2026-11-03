# Estado de VÍA VIVA

Última actualización: **2-nov-2026**. Entrega final: **13-nov-2026**.
Tareas con responsable y fecha: *Issues* de GitHub (`via-viva-usta/via-viva`). Flujo de trabajo: `CONTRIBUTING.md`.

## Fases

| # | Fase | Fechas | Estado |
|---|---|---|---|
| 1 | Repositorio, datos y modelado (BD, OSM, scraping, diagramas) | 26–30 oct | ✅ Hecha |
| 2 | Firmware sin hardware, bot, mapa web, tablero | 28 oct – 2 nov | ✅ Hecha (compila; sin probar en placa) |
| 3 | Hardware y recorridos (montaje, pruebas por sensor, phyphox, E1–E4) | 2–6 nov | 🟡 En curso |
| 4 | Modelos: detector int8 en el nodo y modelo de riesgo | 3–8 nov | 🟡 Cadena lista con datos sintéticos; faltan datos reales |
| 5 | Validación en campo (top-10 de riesgo vs. 10 al azar) | 6–9 nov | ⬜ Pendiente |
| 6 | Entrega: tablero y mapa con datos reales, informe, póster, video, pitch | 9–13 nov | 🟡 Esqueletos listos |

Decisiones vigentes: `CLAUDE.md` (sección 1). Si la Alcaldía no entrega datos antes del **9-nov**, el modelo de riesgo se
entrena con los tramos revisados en recorridos + los reportes del bot (plan B).

## Hecho

| Área | Qué | Dónde |
|---|---|---|
| C | Esquema SQLite (8 tablas), capa de acceso, reconstrucción desde cero con PowerShell | `db/` |
| C | Grafo de Tunja (5 775 tramos, 4 054 nodos), barrios (154), elevación y pendiente, lluvia IDEAM, noticias | `etl/` |
| C | Recorridos de phyphox → map-matching → `tramos_revisados.csv` y eventos | `etl/recorridos.py` |
| C | Modelo de riesgo (logística y bosque, validación espacial por barrios) | `risk_model/` |
| C | Bot de Telegram (foto + ubicación + tipo, número de reporte, estado) | `bot/` |
| C | Mapa web estático (Leaflet) y tablero Java (hash, heap, BFS) | `web/`, `dashboard-java/` |
| A | Firmware ESP32 normal: ADXL345 (FIFO + DMA ping-pong), MPU-6050, VL53L0X, GPS, microSD, botón, Wi-Fi + página web | `firmware/nodo-sensores/` |
| A/B | Detector por umbrales y maniobras (igual en C y en Python) | `src/detector_umbral.h`, `analysis/detector_umbral.py` |
| A | Simulación en Wokwi (ESP32, MPU-6050, microSD, botón, LED) | `firmware/nodo-sensores/wokwi/` |
| A | Esqueleto ESP32-CAM (PING / FOTO, difuminado total) y programación con CP2102 | `firmware/nodo-camara/` |
| B | Notebook de phyphox: espectro, características, clasificador leave-one-drive-out | `analysis/` |
| D | Diagramas Mermaid, propuesta IEEE | `docs/` |

## Probado y no probado

| Pieza | Probado | NO probado |
|---|---|---|
| Base de datos | Reconstrucción completa desde una copia limpia (305 s) | PostgreSQL/PostGIS (solo preparado) |
| ETL OSM / IDEAM / barrios / elevación | Corrida real contra las fuentes | — |
| Noticias | Lectura de RSS y robots.txt | Ninguna noticia relevante todavía |
| Recorridos | Con recorridos **sintéticos** sobre calles reales (26/28 tramos con hueco recuperados) | Con un export real de phyphox |
| Modelo de riesgo | Flujo completo con etiquetas **inventadas** (DEMO) | Con etiquetas reales (hay 0) |
| Bot | Lógica con base temporal; app con token falso | Con Telegram real (falta el token en `.env`) |
| Mapa web | En navegador con base de prueba | Publicado (no se publica todavía) |
| Tablero Java | Compila con Ant; pruebas de estructuras; captura sin pantalla | Abrirlo en el IDE NetBeans; ratón |
| Firmware nodo y cámara | **Compila** | **Nada en hardware** (la placa llega esta semana) |
| Wokwi | `sketch.ino` compila; `diagram.json` válido | La simulación |

## Falta

- Montar el hardware y correr las pruebas por sensor; medir E1–E4 y la corriente.
- Recorridos reales con phyphox y con el nodo, etiquetados.
- Calibrar el detector por umbrales y entrenar el detector (int8) con datos reales.
- Entrenar el modelo de riesgo con datos reales (Alcaldía o plan B) y validarlo en campo.
- Token del bot y prueba con celulares; publicar el mapa cuando el equipo lo decida.
- Informe final con resultados reales, póster, video y pitch.

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
| TinyGPSPlus, VL53L0X (Pololu) | Firmware | LGPL-2.1 / licencia de Pololu (ver cada librería) |
