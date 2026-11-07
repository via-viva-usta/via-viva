# VÍA VIVA

Detecta, mapea y **predice** huecos, resaltos, impactos y obstáculos en las vías de Tunja (Boyacá, Colombia), con IA en el
borde (un ESP32 en el carro y el celular), reportes ciudadanos por Telegram y un modelo de riesgo por tramo de calle.
Proyecto Integrador 2026-2 · Ingeniería de Datos e Inteligencia Artificial · Universidad Santo Tomás, Seccional Tunja.
**No** genera multas ni lee placas.

![Tablero de VÍA VIVA: reportes y eventos ordenados por prioridad con un montículo (datos DEMO)](docs/img/tablero_reportes.png)

*Tablero Java (autoridad) con datos **DEMO** marcados: reportes y eventos ordenados con un montículo por
severidad × tránsito × reincidencia, ranking de riesgo y corredores con BFS. Mapa: `docs/img/tablero_mapa.png`.*

## Arrancar en 3 pasos (Windows, PowerShell)

1. **Clonar e instalar** (una vez; Python 3.11, JDK 21+, ver `CONTRIBUTING.md`):
   ```powershell
   git clone https://github.com/via-viva-usta/via-viva.git; cd via-viva
   copy .env.example .env      # y poner el token del bot si se va a usar (nunca se sube)
   foreach ($m in "etl","bot","dataset") { py -3.11 -m venv "$m\.venv"; & "$m\.venv\Scripts\python" -m pip install -r "$m\requirements.txt" }
   ```
2. **Base de datos** (OpenStreetMap, barrios, pendiente, lluvia IDEAM; ~5 min con internet):
   ```powershell
   .\db\reconstruir.ps1
   ```
3. **Todo en un comando** (tablero, mapa web, bot, clasificador para el celular y, si se pide, la captura en vivo):
   ```powershell
   .\iniciar.ps1                                                         # o -Demo para la base con datos DEMO
   .\iniciar.ps1 -Reproducir data\raw\phyphox\<grabación>.zip            # demo sin carro, con una grabación de phyphox
   .\iniciar.ps1 -Phyphox http://172.20.10.1:8080                        # en el carro, con el iPhone (acceso remoto)
   ```

Pruebas: `dataset\.venv\Scripts\python -m pytest` (también corren en GitHub Actions con cada push).

## Cómo funciona

| Pieza | Qué hace | Dónde |
|---|---|---|
| **Nodo en el carro** | ESP32 + ADXL345 (FIFO + DMA) + MPU-6050 + VL53L0X + GPS + DHT22/BH1750; detector por umbrales y red int8; página web con gráfica en vivo | `firmware/` |
| **Captura en vivo (celular)** | phyphox en el iPhone por el acceso remoto: CSV en vivo, etiquetas con el teclado, mapa y contador de eventos | `herramientas/captura_phyphox_remoto.py` |
| **Fotos (celular)** | Dataset propio de 9 clases con GPS y clima, tarjeta ArUco para la escala, CNN int8 que corre en el navegador del celular | `dataset/`, `web/clasificador/` |
| **Reportes ciudadanos** | Bot de Telegram: foto + ubicación → número de reporte; la CNN sugiere la clase | `bot/` |
| **Datos y riesgo** | ETL → SQLite → modelo de riesgo por tramo validado por barrios (plan B de etiquetas) | `etl/`, `db/`, `risk_model/` |
| **Tablero y mapa** | Java Swing con estructuras propias (tabla hash, montículo, BFS, geohash) y mapa web estático | `dashboard-java/`, `web/` |

**Estado honesto:** qué está probado con datos reales y qué no, en [`docs/ESTADO.md`](docs/ESTADO.md). Lo SINTÉTICO y lo
DEMO siempre van marcados y no se presentan como resultados. Contexto técnico completo: [`CLAUDE.md`](CLAUDE.md).

## Estructura

| Carpeta | Contenido |
|---|---|
| `firmware/` | PlatformIO, ESP32 `esp32dev` (nodo de sensores) y pruebas por sensor |
| `herramientas/` | Captura en vivo de phyphox y validador de lo que llega del campo |
| `analysis/` | Señales, detector por umbrales, entrenamiento del detector del nodo, conversor de vueltas |
| `dataset/` | Fotos: ingesta, planilla, etiquetador, escala ArUco, CNN, datasets externos |
| `etl/`, `db/`, `risk_model/` | OpenStreetMap, scraping, SQLite, recorridos y modelo de riesgo |
| `bot/`, `web/`, `dashboard-java/` | Bot de Telegram, mapa web y clasificador del celular, tablero NetBeans |
| `docs/` | Estado, montaje, protocolo de fotos, demo, presupuesto, diagramas; lo obsoleto en `docs/archivo/` |
| `futuro/` | Trabajo futuro: ESP32-CAM, láser de cuadrícula, OBD2 |
| `tests/` | Pruebas pytest |

Los datos (`data/`), las fotos y los secretos (`.env`, `secretos.h`) **no** se suben al repositorio.

---

## Summary (English)

**VÍA VIVA** is a low-cost edge-AI system that detects, maps and predicts road hazards (potholes, speed bumps, severe impacts
and obstacles) in Tunja, Colombia. A vehicle-mounted ESP32 node with an accelerometer, IMU, laser time-of-flight sensor and
GPS classifies events on-device and logs temperature, humidity and light; a smartphone running phyphox streams live
accelerometer, gyroscope and GPS data to a laptop, where the co-driver labels hazards from the keyboard. The smartphone is
also the edge device for images: an own dataset of geotagged photos of nine road classes, an ArUco card for metric scale and
an int8 convolutional classifier that runs in the phone's browser. An ETL pipeline merges node events, citizen reports
(Telegram bot), web-scraped public sources and the OpenStreetMap street graph into SQLite. A georeferenced model estimates
the risk of unreported hazards per street segment, and a Java Swing dashboard ranks inspections and repairs for the
authorities. The system does not issue fines or read license plates.

Integrative Project 2026-2 — Data Engineering and AI, Universidad Santo Tomás (Tunja).
