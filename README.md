# VÍA VIVA

**Las calles de Tunja, en tiempo real.**

VÍA VIVA detecta, mapea y **predice** huecos, resaltos, impactos y obstáculos en las vías de Tunja (Boyacá, Colombia).
Es el Proyecto Integrador 2026-2 de Ingeniería de Datos e Inteligencia Artificial, Universidad Santo Tomás, Seccional Tunja.

## Cómo funciona

1. **Nodo a bordo (IA en el borde).** Un ESP32 con acelerómetro, unidad inercial, láser de distancia y GPS va en un carro,
   clasifica eventos (hueco, resalto, impacto fuerte) y mide la rugosidad de la vía. Una ESP32-CAM toma una foto de evidencia
   **solo cuando hay evento** y difumina placas y rostros antes de que la imagen salga del nodo.
2. **Reportes ciudadanos.** Un bot de Telegram recibe reportes con foto y ubicación donde el carro no pasa.
3. **ETL.** Une eventos del nodo, reportes ciudadanos, fuentes públicas (scraping responsable) y el grafo de calles de
   OpenStreetMap en una base SQLite.
4. **Modelo de riesgo.** Estima, por cada tramo de calle, la probabilidad de huecos aún no reportados.
5. **Tablero y mapa.** Un tablero en Java Swing prioriza inspecciones y reparaciones para la autoridad; un mapa público muestra
   el estado de los reportes.

VÍA VIVA **no** genera multas ni lee placas.

## Estructura del repositorio

| Carpeta | Contenido |
|---|---|
| `docs/` | Diseño, propuesta IEEE y diagramas (Mermaid) |
| `firmware/nodo-sensores/` | PlatformIO, ESP32 `esp32dev` (sensores, detección, página web del nodo) |
| `firmware/nodo-camara/` | PlatformIO, ESP32-CAM (foto de evidencia) |
| `db/` | Esquema SQLite |
| `etl/` | OpenStreetMap, scraping, limpieza y carga |
| `analysis/` | Notebooks de señales y clasificador |
| `risk_model/` | Modelo predictivo por tramo |
| `bot/` | Bot ciudadano de Telegram |
| `web/` | Mapa web estático (Leaflet) |
| `report/` | Informe final IEEE (LaTeX) |
| `dashboard-java/` | Tablero Java Swing (NetBeans, Ant) |
| `data/` | Solo muestras pequeñas y anonimizadas |

Cada carpeta tiene un `README.md` con su estado.

## Primeros pasos

```bash
git clone https://github.com/via-viva-usta/via-viva.git
cd via-viva
cp .env.example .env        # y llenar los valores
```

- Python (ETL y análisis): ver `etl/README.md` (entorno virtual `.venv` + `requirements.txt`).
- Firmware: abrir la carpeta del nodo en VS Code con la extensión PlatformIO.
- Tablero: abrir `dashboard-java/` en Apache NetBeans como proyecto *Java with Ant*.

## Datos y privacidad

- Los datos crudos (`data/raw/`) y los datos de entidades públicas (`data/alcaldia/`) **no** se suben al repositorio.
- Se guardan eventos, no trayectorias completas de los conductores.
- Las fotos se difuminan en el nodo (Ley 1581 de 2012). La fotodetección con fines de sanción está regulada por la
  Ley 1843 de 2017 y está fuera del alcance del proyecto.
- Los tokens y claves van en `.env` (ver `.env.example`).

---

## Summary (English)

**VÍA VIVA** is a low-cost edge-AI system that detects, maps and predicts road hazards (potholes, speed bumps, severe impacts
and obstacles) in Tunja, Colombia. A vehicle-mounted ESP32 node with an accelerometer, IMU, laser time-of-flight sensor and
GPS classifies events on-device, and an ESP32-CAM captures anonymized evidence only when an event occurs. An ETL pipeline merges
node events, citizen reports (Telegram bot), web-scraped public sources and the OpenStreetMap street graph into SQLite.
A georeferenced model estimates the risk of unreported hazards per street segment, and a Java Swing dashboard ranks inspections
and repairs for the authorities. The system does not issue fines or read license plates.

Integrative Project 2026-2 — Data Engineering and AI, Universidad Santo Tomás (Tunja).
