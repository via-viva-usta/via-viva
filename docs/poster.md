# Contenido del póster (por secciones)

Formato sugerido: 70 × 100 cm vertical, 3 columnas. Identidad: gris asfalto, amarillo señal, verde azulado para
"reparado"; severidad con color **y** forma (legible con daltonismo). Idioma: inglés (como el pitch), con el título
también en español. Las cifras marcadas `[PENDIENTE: dato real]` se llenan solo con números medidos.

## Encabezado

- **VÍA VIVA** — *Every pothole, on the map.* / *Las calles de Tunja, en tiempo real.*
- Edge AI · Road hazard detection · Georeferenced risk map
- Autores, programa (Ingeniería de Datos e IA, 2.º semestre), Universidad Santo Tomás, Seccional Tunja, 2026-2.
- Logo de la USTA y QR al repositorio (cuando sea público) o al mapa web.

## Columna 1 — Problema y solución

**Problem.** Road damage in Tunja is surveyed by hand; fixed enforcement cameras do not see the road surface.
(Una foto de un hueco real de Tunja, sin placas ni rostros.)

**Solution in one line.** A node in a car detects potholes on the device; citizens report the rest; a model predicts
where unreported damage is likely.

**Diagrama** de arquitectura (de `docs/diagramas/01_arquitectura.md` o la Fig. 1 del informe): nodo → ETL/SQLite →
modelo de riesgo → tablero y mapa; bot ciudadano como segunda fuente.

## Columna 2 — Cómo funciona (las tres materias)

**Data acquisition (SADP).** ADXL345 at 200 Hz, sampling rate chosen from the spectrum ([PENDIENTE: f95 medido]),
GPS synchronization, threshold detector + gyroscope maneuvers. Gráfica: un evento real (señal + disparo).

**Computer architecture.** ESP32 dual core; VSPI + FIFO + watermark interrupt + DMA ping-pong; separate HSPI for the
microSD (GPIO matrix to avoid boot pins). Tabla corta E1–E4 con valores medidos ([PENDIENTE: E1–E4]).
Dato ya calculado: red int8 = **872 B** de pesos vs. 3 152 B en float32 (788 parámetros).

**Data structures.** Hash table (graph + geohash index), binary heap (repair ranking), BFS (corridors and high-risk
zones). Dato medido sobre el grafo real: búsqueda del tramo más cercano con geohash = **108 comparaciones vs. 5 775**
por fuerza bruta (mismo resultado en 2 000 búsquedas). Captura del tablero Java.

## Columna 3 — Resultados y negocio

**Detection.** F1 of potholes (leave-one-drive-out): [PENDIENTE]; false positives/km: [PENDIENTE];
vs. threshold detector alone: [PENDIENTE].

**Risk map.** Mapa de calor de Tunja por tramo (del mapa web). Spatial AUC: [PENDIENTE]. Field check: top-10 risk
segments with potholes [PENDIENTE] vs. random [PENDIENTE]. Label source: [Alcaldía / recorridos + bot].

**Data we built.** 5 775 street segments (537.6 km) from OpenStreetMap, slope from SRTM, IDEAM rainfall,
154 neighborhoods; [PENDIENTE: km recorridos y eventos etiquetados] — the first labeled road-vibration dataset of Tunja.

**Privacy by design.** Events, not trajectories · blurred photos · anonymous citizen hash · no fines (Law 1843).

**Business.** Living Lab challenge with the Gobernación de Boyacá; pilot with Tunja's Infrastructure Secretariat;
later SECOP II subscription + fleet kits. Cost of one node: ≈ 330 000 COP.

## Pie

Créditos de datos: © OpenStreetMap contributors (ODbL), IDEAM y Alcaldía de Tunja (datos abiertos, CC BY-SA 4.0),
SRTM (NASA). Agradecimientos a docentes y entidades.
