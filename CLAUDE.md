# CLAUDE.md — VÍA VIVA (contexto para Claude Code)

Lee este archivo completo antes de trabajar. Es la fuente de verdad técnica del repositorio.

## 1. Qué es el proyecto
VÍA VIVA es el Proyecto Integrador 2026-2 (2.º semestre, Ingeniería de Datos e IA, Universidad Santo Tomás, Seccional Tunja).
Detecta, mapea y **predice** huecos, resaltos, impactos y obstáculos en las vías de Tunja (Colombia).

- **Nodo en el carro (IA en el borde):** ESP32 (WROOM-32) + acelerómetro ADXL345 (SPI) + MPU-6050 (I2C) + láser VL53L0X (I2C) +
  GPS NEO-6M (UART) + microSD (SPI) + pulsador de etiquetado. Clasifica eventos con un modelo int8 y mide rugosidad y
  profundidad. Una ESP32-CAM (OV2640) toma foto de evidencia solo cuando hay evento y difumina placas y rostros.
- **PC / servidor:** ETL (nodo + reportes ciudadanos + scraping + OpenStreetMap) → SQLite → modelo predictivo de riesgo por
  tramo de calle → tablero en Java Swing + mapa público. Bot ciudadano (Telegram) para reportes con foto y ubicación.
- **No** genera multas ni lee placas.

**Decisiones vigentes (2-nov-2026):**
- Placa principal: **ESP32 normal (WROOM-32, DevKit de 30 pines, `esp32dev`)**. La ESP32-S3 quedó descartada.
- La ESP32-CAM se programa con un adaptador USB-TTL **CP2102** (sin base MB).
- Presupuesto aproximado: **330.000 COP**.
- Atención al ciudadano: **bot de Telegram + mapa web estático**, sin backend. Para la demo el bot corre en el portátil.
- Base de datos: **SQLite** (capa de acceso en `db/acceso.py` para migrar a PostgreSQL/PostGIS después).
- Datos: recorridos normales en carro a **máx. 30 km/h**; primero con el celular (phyphox) y luego con el nodo.
- Modelo de riesgo: si la Alcaldía no entrega datos antes del 9-nov, se entrena con los tramos revisados en los
  recorridos + los reportes del bot.
- Flujo de trabajo: ramas y Pull Requests (ver `CONTRIBUTING.md`). Estado del proyecto en `docs/ESTADO.md`.

Documentos de referencia en `docs/`:
- `docs/03_VIA_VIVA_desarrollo.md` — diseño completo (adquisición, arquitectura, procesamiento, estructuras, capa predictiva).
- `docs/propuesta/main.tex` + `referencias.bib` — propuesta IEEE (inglés, 2 columnas, 4 páginas).

## 2. Materias que el código debe evidenciar
| Materia | Qué debe quedar demostrable en el código |
|---|---|
| Sistemas de Adquisición (SADP) | Muestreo justificado (espectro/Nyquist), filtros, sincronía GPS, características de señal, métricas de detección |
| Arquitectura del Computador | Buses SPI/I2C/UART, FIFO + interrupción + DMA ping-pong, doble núcleo (FreeRTOS), RAM/Flash, latencia, consumo |
| Estructuras de Datos | Cola/búfer circular (nodo), hash espacial (geohash), grafo de calles con BFS/DFS, heap de prioridad, ABB/TreeMap, análisis de complejidad |
| Requisitos extra | ETL, web scraping, modelo de IA ligero, demo |

## 3. Estructura objetivo del repositorio
```
via-viva/
├── CLAUDE.md                 # este archivo
├── README.md                 # presentación pública (español + resumen en inglés)
├── .gitignore
├── docs/                     # diseño, propuesta, diagramas (docs/diagramas/*.md con Mermaid)
├── firmware/
│   ├── nodo-sensores/        # PlatformIO, ESP32 esp32dev (Arduino framework); pruebas/ = un programa por sensor
│   └── nodo-camara/          # PlatformIO, ESP32-CAM AI-Thinker
├── db/schema.sql             # SQLite: tramos, eventos, reportes, fuentes_externas, riesgo
├── etl/                      # Python: OSM Tunja, scraping, limpieza, carga a SQLite
├── analysis/                 # Notebooks: señales (phyphox y nodo), espectro, clasificador
├── risk_model/               # Modelo predictivo georreferenciado por tramo
├── bot/                      # Bot de Telegram (token en .env, nunca en el repo)
├── web/                      # Mapa web estático (Leaflet), sin backend
├── report/                   # Informe final IEEE (LaTeX)
├── dashboard-java/           # Proyecto NetBeans (Java with Ant), Java 21, Swing
└── data/                     # SOLO muestras pequeñas y anonimizadas; ver regla de datos
```

## 4. Reglas obligatorias
1. **Datos:** `data/raw/`, `data/alcaldia/` y cualquier dato de terceros van en `.gitignore`. Los datos de la Alcaldía no se
   publican sin permiso. En el repo solo se suben muestras pequeñas y sin datos personales.
2. **Secretos:** tokens y claves solo en `.env` (ignorado). Proveer `.env.example`.
3. **Privacidad:** nunca guardar trayectorias completas de conductores en la base final; solo eventos. Fotos siempre difuminadas.
4. **Reproducibilidad:** Python en entorno virtual (`.venv`) con `requirements.txt`; firmware con PlatformIO (`platformio.ini`).
5. **Verificación:** todo resultado numérico se calcula con código (no se inventan cifras). Si algo no se pudo probar en
   hardware real, se dice explícitamente en el README del módulo.
6. **Idioma:** código y comentarios en español sencillo; nombres de variables en inglés o español, pero consistentes.
7. **Commits pequeños** con mensajes claros en español (`feat(etl): descarga del grafo de Tunja`).
8. **Java:** el tablero debe abrir en Apache NetBeans 25 como proyecto *Java with Ant* (entorno del curso de Estructuras de Datos).

## 5. Hardware y pines (verificar contra la placa real antes de soldar)
Placa principal: **ESP32 DevKit de 30 pines (ESP32-WROOM-32, 4 MB flash, sin PSRAM, 520 KB SRAM), entorno `esp32dev`**.
Pines prohibidos o limitados: **0, 2, 5, 12, 15** (arranque), **6–11** (flash interna), **34–39 solo entradas y sin
pull-up interno**, 1 y 3 (UART0 / monitor serie).

| Señal | GPIO ESP32 | Bus |
|---|---|---|
| ADXL345 SCK / MISO / MOSI / CS | 18 / 19 / 23 / 4 | VSPI (SPI3) — CS en 4 porque el CS nativo de VSPI es el 5 (arranque) |
| ADXL345 INT1 (watermark FIFO) | 34 | interrupción (solo entrada; el INT1 del ADXL345 es push-pull) |
| microSD SCK / MISO / MOSI / CS | 14 / 27 / 13 / 32 | HSPI (SPI2) por la matriz GPIO — ver nota |
| I2C SDA / SCL (MPU-6050 0x68, VL53L0X 0x29) | 21 / 22 | I2C |
| GPS NEO-6M: TX del GPS → RX / RX del GPS ← TX | 16 / 17 | UART2 (9600 baud) |
| Enlace a ESP32-CAM: TX / RX | 25 / 35 | UART1 (115200 baud) |
| Pulsador de etiquetado | 26 | INPUT_PULLUP |
| LED de estado | 33 | salida |

**Conflicto de buses (explicado):** los pines nativos (IO_MUX) de HSPI son 14/12/13/15, pero 12 y 15 son de arranque
(el 12 fija el voltaje de la flash: una microSD con pull-up en MISO puede impedir el arranque). Por eso la microSD usa
HSPI enrutado por la **matriz GPIO** a 14/27/13/32. Costo: por la matriz el SPI llega a ~26 MHz como máximo (en vez de
80 MHz), de sobra para la microSD (se usa a 10 MHz). El ADXL345 sigue en VSPI: los dos buses quedan separados.

ESP32-CAM (AI-Thinker): se programa con un **CP2102** (5V→5V, GND→GND, TX del CP2102→U0R/GPIO3, RX→U0T/GPIO1,
GPIO0 a GND al flashear; se quita el puente y se reinicia para correr). Enlace con el nodo: CAM RX = GPIO 13,
CAM TX = GPIO 14 (pines de la microSD interna, que no se usa).

## 6. Parámetros de diseño de la señal
- Muestreo de trabajo: 200 Hz (se valida con espectro de los primeros recorridos; conservar 95 % de la energía).
- FIFO ADXL345: watermark de 31 muestras (el campo tiene 5 bits) → interrupción cada 155 ms a 200 Hz → DMA ping-pong.
- Ventanas por energía/jerk; características: pico, RMS, curtosis, factor de cresta, energía por banda, normalizadas por velocidad.
- Clases: hueco, resalto, impacto fuerte, normal.
- Validación: separar por recorrido (leave-one-drive-out), nunca por ventana.

## 7. Modelo predictivo (capa georreferenciada)
- Unidad: tramo de calle de OpenStreetMap (osmnx), zona piloto de pocos barrios de Tunja.
- Variables por tramo: tipo de vía, superficie, pendiente (modelo de elevación público), lluvia (IDEAM), huecos conocidos
  cercanos (nodo, ciudadanos, inventario de la Alcaldía), accidentalidad, rugosidad y profundidad medidas.
- Modelos: regresión logística y bosque aleatorio. Validación espacial (barrios completos fuera).
- Métricas: AUC espacial (meta ≥ 0,70) y acierto en campo de los 10 tramos de mayor riesgo vs. 10 al azar.

## 8. Experimentos de arquitectura (deben poder ejecutarse desde el firmware)
- E1: polling vs. interrupción por muestra vs. FIFO + DMA ping-pong (jitter, CPU, muestras perdidas, corriente).
- E2: pesos del modelo en flash vs. SRAM (latencia). (La ESP32 normal no tiene PSRAM.)
- E3: float32 vs. int8 (latencia, RAM, flash, F1). La ESP32 normal no tiene instrucciones vectoriales (ESP-NN no aplica).
- E4: I2C (MPU-6050) vs. SPI (ADXL345) (tiempo de lectura, CPU).

## 9. Equipo y áreas
| Área | Principal | Apoyo |
|---|---|---|
| A. Hardware y firmware | Dany Cipamocha | Juan Diego Anzola |
| B. Señales e IA | Juan Felipe García | Andrés Cárdenas |
| C. Datos y plataforma | Andrés Cárdenas | Dany Cipamocha |
| D. Gestión y documento | Andrés Cárdenas | Juan Diego Anzola |
Andrés opera Claude Code; los demás prueban, aportan datos y revisan.

## 10. Calendario (entrega 13-nov-2026)
- 26–30 oct: repo, ETL/OSM, scraping, base de datos, diagramas; llegada y montaje del hardware.
- 28 oct–5 nov: firmware y recorridos de campo.
- 3–6 nov: modelo de detección int8 y modelo de riesgo.
- 6–9 nov: validación en campo.
- 9–13 nov: tablero final, informe, póster, video, pitch.
