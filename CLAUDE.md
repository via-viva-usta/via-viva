# CLAUDE.md — VÍA VIVA (contexto para Claude Code)

Lee este archivo completo antes de trabajar. Es la fuente de verdad técnica del repositorio.

## 1. Qué es el proyecto
VÍA VIVA es el Proyecto Integrador 2026-2 (2.º semestre, Ingeniería de Datos e IA, Universidad Santo Tomás, Seccional Tunja).
Detecta, mapea y **predice** huecos, resaltos, impactos y obstáculos en las vías de Tunja (Colombia).

- **Nodo en el carro (IA en el borde):** ESP32-S3 + acelerómetro ADXL345 (SPI) + MPU-6050 (I2C) + láser VL53L0X (I2C) +
  GPS NEO-6M (UART) + microSD (SPI) + pulsador de etiquetado. Clasifica eventos con un modelo int8 y mide rugosidad y
  profundidad. Una ESP32-CAM (OV2640) toma foto de evidencia solo cuando hay evento y difumina placas y rostros.
- **PC / servidor:** ETL (nodo + reportes ciudadanos + scraping + OpenStreetMap) → SQLite → modelo predictivo de riesgo por
  tramo de calle → tablero en Java Swing + mapa público. Bot ciudadano (Telegram) para reportes con foto y ubicación.
- **No** genera multas ni lee placas.

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
│   ├── nodo-sensores/        # PlatformIO, ESP32-S3 (Arduino framework)
│   └── nodo-camara/          # PlatformIO, ESP32-CAM AI-Thinker
├── db/schema.sql             # SQLite: tramos, eventos, reportes, fuentes_externas, riesgo
├── etl/                      # Python: OSM Tunja, scraping, limpieza, carga a SQLite
├── analysis/                 # Notebooks: señales (phyphox y nodo), espectro, clasificador
├── risk_model/               # Modelo predictivo georreferenciado por tramo
├── bot/                      # Bot de Telegram (token en .env, nunca en el repo)
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

## 5. Hardware y pines (PROPUESTA — verificar contra la placa real antes de soldar)
Placa principal: **ESP32-S3-DevKitC-1 N16R8** (16 MB flash, 8 MB PSRAM octal).
En variantes con PSRAM octal **no usar GPIO 35, 36, 37**. Evitar también 0, 3, 45, 46 (arranque), 19–20 (USB),
26–32 (flash), 43–44 (UART0 / monitor serie).

| Señal | GPIO ESP32-S3 | Bus |
|---|---|---|
| ADXL345 CS / MOSI / SCK / MISO | 10 / 11 / 12 / 13 | SPI2 (FSPI) |
| ADXL345 INT1 (watermark FIFO) | 14 | interrupción |
| microSD CS / MOSI / SCK / MISO | 4 / 5 / 6 / 7 | SPI3 (separado del ADXL345) |
| I2C SDA / SCL (MPU-6050 0x68, VL53L0X 0x29) | 8 / 9 | I2C |
| GPS NEO-6M TX→RX / RX←TX | 17 / 18 | UART1 (9600 baud por defecto) |
| Enlace a ESP32-CAM TX / RX | 15 / 16 | UART2 |
| Pulsador de etiquetado | 1 | INPUT_PULLUP |
| LED de estado | 2 | salida |

ESP32-CAM (AI-Thinker): la cámara ocupa casi todos los pines; el enlace UART con el nodo se define al validar la placa
(candidatos GPIO 13/14 o 14/15, sin usar la microSD interna).
Plan B si no hay ESP32-S3: ESP32 normal (WROOM-32). En ese caso el experimento E3 (instrucciones vectoriales) no aplica.

## 6. Parámetros de diseño de la señal
- Muestreo de trabajo: 200 Hz (se valida con espectro de los primeros recorridos; conservar 95 % de la energía).
- FIFO ADXL345: watermark de 32 muestras → interrupción cada 160 ms a 200 Hz → DMA ping-pong.
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
- E2: pesos del modelo en flash vs. SRAM vs. PSRAM (latencia).
- E3: float32 vs. int8, con y sin ESP-NN (latencia, RAM, flash, F1).
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
