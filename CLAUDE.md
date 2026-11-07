# CLAUDE.md — VÍA VIVA (contexto para Claude Code)

Lee este archivo completo antes de trabajar. Es la fuente de verdad técnica del repositorio.
**Para continuar el trabajo, lee después `docs/ESTADO.md`** (qué está hecho, qué está probado y qué falta por persona)
y los issues abiertos de GitHub. Con esos dos archivos un chat nuevo puede seguir sin más contexto.

Última actualización: **5-nov-2026**. Entrega final: **13-nov-2026**.

## 1. Qué es el proyecto
VÍA VIVA es el Proyecto Integrador 2026-2 (2.º semestre, Ingeniería de Datos e IA, Universidad Santo Tomás, Seccional Tunja).
Detecta, mapea y **predice** huecos, resaltos, impactos y obstáculos en las vías de Tunja (Colombia).

- **Nodo en el carro (IA en el borde):** ESP32 normal (WROOM-32) + acelerómetro ADXL345 (SPI) + MPU-6050 (I2C) +
  láser VL53L0X (I2C) + GPS NEO-6M (UART) + microSD (SPI) + pulsador + **DHT22 y BH1750** (ambiente; el código también acepta un BME280). Detector por
  umbrales + clasificador int8 en el nodo; maniobras con el giroscopio; página web propia (punto de acceso Wi-Fi) para etiquetar.
- **Celular = dispositivo de borde para imágenes (desde el 3-nov):** dataset propio de ≥ 500 fotos de 9 clases con fecha,
  hora, GPS, temperatura y humedad; tarjeta ArUco para la escala; clasificador MobileNetV3 → TFLite int8 (`dataset/`).
  La ESP32-CAM y el CP2102 **salieron del diseño** (`futuro/`).
- **PC / portátil:** ETL (nodo + phyphox + bot + scraping + OpenStreetMap) → SQLite → modelo de riesgo por tramo de calle →
  tablero Java Swing (autoridad) + mapa web estático (ciudadanía). Bot de Telegram para reportes con foto y ubicación.
- **No** genera multas ni lee placas.

## 2. Decisiones vigentes (no reabrir sin hablar con Andrés)

| Fecha | Decisión |
|---|---|
| 13-oct | Reporte con evidencia (no multas); nodo a bordo de vehículos; usuario = autoridad (tablero) + ciudadanía (mapa) |
| 24-oct | Capa predictiva georreferenciada por tramo (sugerencia del docente y comité curricular); láser VL53L0X para profundidad |
| 26-oct | Repositorio privado `via-viva-usta/via-viva`; Python en `.venv`; firmware PlatformIO; tablero NetBeans *Java with Ant* |
| **2-nov** | **Placa principal: ESP32 normal (WROOM-32, DevKit de 30 pines, entorno `esp32dev`).** La ESP32-S3 quedó descartada |
| ~~2-nov~~ | ~~ESP32-CAM se programa con adaptador USB-TTL CP2102~~ → reemplazado el 3-nov (sin ESP32-CAM) |
| ~~2-nov~~ | ~~Presupuesto aproximado 330.000 COP~~ → 268.900 COP el 3-nov (`docs/presupuesto.md`) |
| 2-nov | Atención al ciudadano = **bot de Telegram + mapa web estático, sin backend**; para la demo el bot corre en el portátil |
| 2-nov | Base de datos **SQLite** detrás de la capa de acceso `db/acceso.py` (lista para migrar a PostgreSQL/PostGIS) |
| 2-nov | Datos: recorridos normales en carro a **máx. 30 km/h**; primero celular (**phyphox**), luego el nodo |
| 2-nov | **Ajustes del docente de Arquitectura:** (a) detector por umbrales como línea base y pre-etiquetado; (b) clases de maniobra con el giroscopio (giro izq./der., frenada brusca); (c) servidor web en el ESP32 con botones de etiquetado, Wi-Fi en núcleo 0 y adquisición en núcleo 1 |
| 2-nov | **Plan B de etiquetas del modelo de riesgo:** si la Alcaldía no entrega datos antes del **9-nov**, se entrena con tramos revisados en recorridos (+ visitas) + reportes del bot. Cada corrida registra la fuente (`--fuente auto`) |
| 2-nov | Trabajo en equipo por **ramas y Pull Requests** (`CONTRIBUTING.md`); Andrés revisa y fusiona |
| 2-nov | E2 = pesos en flash vs. SRAM; E3 = float32 vs. int8 (sin PSRAM ni instrucciones vectoriales en la ESP32 normal) |
| ~~3-nov~~ | ~~Informe compilado con MiKTeX por Claude~~ → desde el 5-nov lo edita Juan Diego en Overleaf |
| 3-nov | Cuenta de GitHub del proyecto: **`andresscardens`** (ver sección 11) |
| **3-nov** | **Cambio de plan aprobado por el docente de Arquitectura:** (a) el **módulo láser de cuadrícula** queda como trabajo futuro (no se consigue a tiempo); (b) **dataset propio de fotos con el celular** (≥ 500, ≥ 50 por clase, 9 clases, con fecha, hora, ubicación, tipo, temperatura y humedad); (c) se **eliminan la ESP32-CAM y el CP2102**; se agrega **BME280 (o DHT22) y BH1750** al nodo; (d) **OBD2** (ELM327 Bluetooth, solo lectura) = módulo opcional futuro |
| 3-nov | Clima de cada foto: termohigrómetro (a mano) > nodo (± 30 min) > API Open-Meteo por hora (`fuente_clima`); lluvia IDEAM del día |
| 3-nov | Modelo de fotos: MobileNetV3-Small, división **por sitio** (nunca por foto), TFLite int8. TensorFlow en `%USERPROFILE%\.venvs\vv-modelo` (rutas largas) |
| 3-nov | Presupuesto **268.900 COP** (nuevo por comprar: DHT22 + BH1750 = 30.000) |
| **3-nov** | **Sensor de temperatura y humedad: DHT22 de Ferretrónica** (GPIO 25). No se pide el BME280 a Bogotá (no hay en Ferretrónica). El firmware sigue aceptando un BME280 si aparece |
| **5-nov** | Fotos del dataset con el **iPhone 15 de Juan Diego**; phyphox en el **iPhone 17 de Pipe (~100 Hz)**; el copiloto etiqueta con el **cronómetro del iPhone por vueltas** (`analysis/vueltas_a_etiquetas.py`) |
| 5-nov | Drive del equipo: `VIA_VIVA/02_DATOS/fotos/AAAA-MM-DD_nombre/` y `VIA_VIVA/02_DATOS/phyphox/`; Andrés baja a `data/raw/`. **Planilla de campo** (Google Sheets → CSV en `data/raw/planilla/`) |
| 5-nov | `tipo_via` sale solo de OSM; **`superficie`** (asfalto/concreto/adoquín/destapada) de la planilla o el etiquetador |
| 5-nov | Hugging Face `Duranishhh/baches-carreteras` **no se usa** (licencia no documentada); Kaggle `andrewmvd/pothole-detection` sí (DbCL), falta descargarlo |
| 5-nov | Modelo de fotos con **tf_keras** (Keras 2) por la QAT; se comparan MobileNetV3-Small y **MobileNetV2**; el celular y el bot usan el **mejor int8** (`dataset/salidas/<versión>/info.json`) |
| 5-nov | **INFORME: Claude NO compila ni genera PDF/.docx**; Juan Diego lo edita en **Overleaf**; Claude propone texto en `docs/cambios_informe.md` |
| 5-nov | La Alcaldía apoya de palabra un **piloto** (falta convenio USTA–Alcaldía) |

Documentos de referencia: `docs/03_VIA_VIVA_desarrollo.md` (diseño; con nota del cambio de placa), `docs/archivo/propuesta_ESP32-S3/`
(propuesta entregada, con ESP32-S3: **no se modifica**; archivada el 7-nov), `docs/diagramas/` (Mermaid), `docs/montaje.md`,
`docs/experimentos.md`, `docs/demo.md`, `docs/poster.md`, `docs/ESTADO.md`, `docs/protocolo_fotos.md`,
`docs/presupuesto.md`, `docs/tarjeta_aruco.pdf`, `dataset/README.md`, `futuro/README.md`.

## 3. Materias que el código debe evidenciar
| Materia | Qué debe quedar demostrable | Dónde está |
|---|---|---|
| Sistemas de Adquisición (SADP) | Muestreo justificado (espectro/Nyquist), filtros, sincronía GPS, características, métricas de detección | `analysis/`, `firmware/.../caracteristicas.h` |
| Arquitectura del Computador | SPI/I2C/UART, FIFO + interrupción + DMA ping-pong, doble núcleo FreeRTOS, RAM/flash, latencia, consumo (E1–E4) | `firmware/nodo-sensores/`, `docs/experimentos.md` |
| Estructuras de Datos | Búfer circular y colas (nodo), tabla hash + geohash, grafo con BFS, heap, análisis de complejidad | `dashboard-java/`, `firmware/nodo-sensores/include/bufer_circular.h`, `etl/geohash.py` |
| Requisitos extra | ETL, web scraping, IA ligera, demo | `etl/`, `analysis/`, `dataset/`, `docs/demo.md` |

Pendiente del diseño original de Estructuras: bitácora por fechas con `TreeMap` y "peligros" agrupados (cuando haya eventos).

## 4. Estructura del repositorio
```
via-viva/
├── CLAUDE.md · README.md · CONTRIBUTING.md · .gitignore · .gitattributes · .env.example
├── docs/            diseño, propuesta, diagramas Mermaid, ESTADO, montaje, experimentos, demo, póster
├── firmware/
│   ├── nodo-sensores/   PlatformIO esp32dev: src/ (módulos), include/ (pines.h, config.h, secretos.example.h),
│                        pruebas/ (un programa por sensor), wokwi/ (simulación), diagram.json + wokwi.toml
├── db/              schema.sql (8 tablas), acceso.py (capa de acceso), reconstruir.ps1
├── etl/             osm_tunja, barrios_tunja, elevacion, scraping/ (clima IDEAM, noticias), recorridos, recorrido_sintetico
├── analysis/        senales.py, detector_umbral.py, modelo_cnn.py, entrenar_detector.py, experimentos.py, notebook
├── risk_model/      variables.py (tabla de variables por tramo), modelo.py (logística y bosque, plan B)
├── bot/             bot.py, reportes.py, cambiar_estado.py
├── web/             index.html (Leaflet) + exportar.py → datos.js; clasificador/ (CNN en el navegador del celular)
├── herramientas/    validar_campo.py (revisión de phyphox, fotos y planilla antes de procesar)
├── iniciar.ps1      todo en un comando (tablero, mapa, bot, clasificador, captura en vivo)
├── demo/            datos_demo.py (base DEMO aparte)
├── tests/           pytest (34 pruebas) · .github/workflows/ (pytest y PlatformIO)
├── dataset/         fotos: comun, tarjeta_aruco, ingesta, planilla, etiquetador, escala, modelo, clasificar, externos, sintetico
├── futuro/          trabajo futuro: nodo-camara (ESP32-CAM), láser de cuadrícula, OBD2
├── dashboard-java/  NetBeans Ant, Java 21: estructuras/ (TablaHash, MonticuloMax, GrafoCalles, IndiceGeohash)
├── report/          main.tex (IEEE), referencias.bib, figuras/generar.py, tablas/ (generadas por experimentos.py)
└── data/            solo README y muestras; raw/, alcaldia/, osm/, campo/, fotos_bot/, procesado*/ y la base .db ignorados
```

## 5. Reglas obligatorias
1. **Datos:** `data/raw/`, `data/alcaldia/`, `data/campo/`, `data/osm/`, `data/fotos_bot/` y `*.db` están en `.gitignore`.
   Los datos de la Alcaldía no se publican sin permiso. En el repo solo muestras pequeñas sin datos personales.
2. **Secretos:** solo en `.env` (ignorado): `TELEGRAM_BOT_TOKEN`, `BOT_SAL_HASH`, `VIA_VIVA_DB_URL`, etc.
   Clave del punto de acceso del nodo en `firmware/nodo-sensores/include/secretos.h` (ignorado). **Nunca** pedir ni mostrar
   tokens en el chat; para que el usuario pegue un secreto, abrirle `.env` en el editor.
3. **Privacidad:** a la base final solo llegan eventos y listas de tramos revisados, nunca trayectorias. Fotos difuminadas;
   las fotos del bot no se publican; del usuario del bot solo se guarda un hash con sal.
4. **Reproducibilidad:** venvs + `requirements.txt`; firmware con `platformio.ini`; base reconstruible con `db/reconstruir.ps1`.
5. **Verificación:** todo número sale de código o medición. **No se inventan resultados.** Lo sintético se marca SINTÉTICO/DEMO
   y nunca se reporta como resultado; en el informe lo que falta va como `\pendiente{...}` (rojo).
6. **Idioma:** código, comentarios y documentos en español sencillo; el informe y el pitch en inglés.
7. **Commits pequeños** en español con prefijo (`feat(etl): ...`, `fix(firmware): ...`, `docs: ...`), con la línea
   `Co-Authored-By` cuando los hace Claude.
8. **Java:** el tablero debe abrir en Apache NetBeans 25 como *Java with Ant*, Java 21.

## 6. Hardware y pines FINALES (ESP32 DevKit 30 pines, WROOM-32)
4 MB de flash, 520 KB de SRAM, sin PSRAM. Pines prohibidos o limitados: **0, 2, 5, 12, 15** (arranque), **6–11** (flash),
**34–39** solo entradas y sin pull-up, 1 y 3 (monitor serie). Fuente única en el código: `firmware/nodo-sensores/include/pines.h`.

| Señal | GPIO | Bus / nota |
|---|---|---|
| ADXL345 SCK / MISO / MOSI / CS | 18 / 19 / 23 / 4 | VSPI (SPI3_HOST) con `spi_master` + DMA; CS en 4 porque el nativo (5) es de arranque |
| ADXL345 INT1 (watermark) | 34 | Solo entrada; el INT1 del ADXL345 es push-pull |
| microSD SCK / MISO / MOSI / CS | 14 / 27 / 13 / 32 | HSPI (SPI2) **por la matriz GPIO** (los nativos 12 y 15 son de arranque); 10 MHz |
| I2C SDA / SCL | 21 / 22 | MPU-6050 (0x68), VL53L0X (0x29), **BH1750 (0x23, ADDR a GND)**; BME280 opcional (0x76/0x77, no se compró); 400 kHz |
| GPS NEO-6M (TX del GPS → RX / RX ← TX) | 16 / 17 | UART2, 9600 baud |
| **DHT22** DATA (sensor elegido el 3-nov) | 25 | Un hilo, pull-up 10 kΩ a 3V3. El 25 y el 35 quedaron libres al retirar la ESP32-CAM |
| Pulsador | 26 | INPUT_PULLUP, a GND, antirrebote 250 ms |
| LED | 33 | salida |

**Ambiente (3-nov):** controladores propios en `include/ambiente.h` (compensación entera de Bosch, verificada con el ejemplo
de la hoja de datos en `pruebas/prueba_bme280.cpp`). Sensor comprado: **DHT22**; si algún día se pone un BME280, el código lo prefiere (y si su ID es 0x58 es un BMP280 sin humedad).
Lectura cada `PERIODO_AMBIENTE_MS` = 10 s en la tarea I2C → `ambiente_NNN.csv` + tarjeta "Ambiente" de la página web.
El sensor va **fuera de la caja** (la ESP32 lo calienta) y, para clima, fuera de la cabina del carro.
**ESP32-CAM y CP2102: fuera del diseño** (código en `futuro/nodo-camara/`).

**Montaje:** MPU-6050 con **X hacia adelante y Z hacia arriba** (si no, cambiar `EJE_*`/`SIGNO_*` en `config.h`); ADXL345 y
MPU rígidos a la baquela; detalles, orden de prueba y errores típicos en `docs/montaje.md`.

## 7. Firmware del nodo (`firmware/nodo-sensores`)
- **Tareas:** núcleo 1 = `tareaAdquisicion` (prioridad 20) y `tareaProcesamiento` (10); núcleo 0 = Wi-Fi + web, GPS, I2C +
  maniobras + ambiente (cada 10 s), microSD, estadísticas. `loop()` se elimina para medir el ocio del núcleo 1.
- **Adquisición:** ADXL345 a 200 Hz, ±16 g resolución completa (3,9 mg/LSB), FIFO *stream* con **watermark 31** (el campo tiene
  5 bits → interrupción cada 155 ms), lote por DMA a 1,5 MHz (≤ 1,6 MHz no necesita pausa entre lecturas de la FIFO),
  búfer **ping-pong** de 2 mitades con semáforos; `bloques_perdidos` si el procesamiento se atrasa.
- **Modo de adquisición (E1) por entorno:** `esp32dev` = FIFO+DMA (normal), `e1_polling`, `e1_int_muestra`.
- **Detector por umbrales** (`src/detector_umbral.h`, igual a `analysis/detector_umbral.py`): evento si velocidad GPS >
  **5 km/h** y el pico a pico de la aceleración vertical en **50 ms** > **6 ×** RMS de fondo (promedio exponencial, τ = **2 s**,
  usando el valor anterior) y > **0,30 g**, con **1 s** refractario y 2 s de calentamiento. Señal = \|a\| − 1 g. **Sin calibrar.**
- **Maniobras** (`src/maniobras.h`): giro si \|ω vertical filtrada (τ 0,25 s)\| > **15 °/s** durante **1 s** con velocidad > 5 km/h
  (positivo = izquierda); frenada si aceleración longitudinal < −**0,30 g** durante **0,5 s** o caída GPS > **2,5 m/s²**. Un golpe
  durante una maniobra se atribuye a la maniobra.
- **Clase del evento:** hoy **provisional por reglas** (`clasificarProvisional`); el modelo int8 existe pero está entrenado con
  datos SINTÉTICOS (`MODELO_SINTETICO 1` en `src/modelo_cnn.h`): sirve para medir latencia, no para clasificar.
- **Página web** (`src/servidor_web.cpp`): red `VIA-VIVA-NODO`, http://192.168.4.1, botones Hueco/Resalto/Otro, "modo mesa"
  (ignora la velocidad para probar sin carro), estado de sensores, modo E1 y tarjeta **Ambiente** (°C, % HR, hPa, lx).
- **microSD por sesión:** `crudo_NNN.csv` (t_us, cuentas), `eventos_NNN.csv`, `gps_NNN.csv`, `etiquetas_NNN.csv`
  (tipo, origen web/botón), `ambiente_NNN.csv` (utc_fix + ms_desde_fix, lugar, sensor, °C, % HR, hPa, lx), `exp_NNN.csv`.
- **Experimentos:** E1 cada 5 s; E2/E3/E4 y memoria **al arrancar** antes de crear tareas (`src/experimentos.cpp`).
- **Página web (5-nov):** gráfica en vivo de |a|−1 g (`/senal`, 20 Hz, búfer con spinlock), umbrales K/piso/v_min/refractario
  ajustables y guardados en NVS (`/ajustes`, filas AJU en `exp`), lista y descarga de los CSV por Wi-Fi (`/archivos`,
  `/descargar`, con `mutexSD`), estado de microSD/GPS y causa del reinicio.
- **Robustez (5-nov):** watchdog de 10 s en adq/proc/gps/i2c/sd; GPS sin bytes 5 s → reinicia UART2; fijación vieja 5 s →
  velocidad 0; microSD con sesión en NVS, reintento cada 10 s y remontaje si falla una escritura (`max_files` 8: antes
  `exp_NNN.csv` no abría); pérdida por corte ≤ 1 s más colas. **LED** (`led_estado.cpp`): fijo = arranque; lento = OK;
  1–4 destellos = sin fijación / GPS sin datos / SD / ADXL; rápido = evento. Todo **[VALIDAR EN PLACA]**.
- Tamaño (esp32dev, 5-nov): RAM estática 66 348 B (20,2 %), flash 944 269 B (48,0 %), partición `min_spiffs.csv`.
  Wokwi: `wokwi-esp32-devkit-v1` + DHT22.

## 8. Señal, detector y entrenamiento
- Muestreo de trabajo 200 Hz (hipótesis; se valida con el espectro de los primeros recorridos: 95 % de la energía).
- Clases: normal, hueco, resalto, impacto_fuerte (+ maniobras: giro_izquierda, giro_derecha, frenada_brusca).
- Características del nodo (`caracteristicas.h`, réplica exacta en `entrenar_detector.py`): pico, RMS, curtosis, factor de cresta,
  jerk máximo, signo del pico (+ velocidad) en ventana de 2 s (1,5 s antes, 0,5 s después del disparo).
- Modelos: bosque (10 árboles, profundidad ≤ 6, exportado con **emlearn** a `src/modelo_bosque.h`) y red 1D
  (`analysis/modelo_cnn.py`: conv 1→8 k7 p2, conv 8→16 k5 p2, promedio, densa 16→4; **788 parámetros; 3 152 B float32,
  872 B int8**) con cuantización int8 propia, idéntica en Python y en C (redondeo floor(v+0,5)).
- **Validación siempre leave-one-drive-out**, por ventana y por evento, comparada con el detector por umbrales solo.
- Un comando: `analysis\.venv\Scripts\python analysis\entrenar_detector.py` (datos reales) o `--sintetico` (prueba).

## 9. Datos y base (SQLite)
- Tablas: `tramos`, `eventos` (clases de vía y maniobra; `origen` nodo/phyphox/simulado), `reportes` (estado nuevo →
  confirmado → en_reparacion → reparado / descartado), `fuentes_externas`, `riesgo` (con `fuente_etiquetas`), `nodos`,
  `barrios`, `variables_tramo`. Migración automática de columnas nuevas en `db/acceso.py` (`COLUMNAS_NUEVAS`).
- Conexión desde `.env`: `VIA_VIVA_DB_URL=sqlite:///data/via_viva.db`. Siempre abrir con `db.acceso.conectar()`.
- Fuentes reales cargadas: OSM (5 775 tramos, 4 054 nodos, 537,6 km), barrios de la Alcaldía en datos abiertos (154),
  SRTM 30 m vía OpenTopoData (pendiente de 4 659 tramos), lluvia IDEAM (5 estaciones ≤ 15 km). Licencias en `docs/ESTADO.md`.
- **Recorridos** (`etl/recorridos.py`): phyphox + `_etiquetas.csv` → detector por umbrales (pre-etiquetas) → map-matching al
  tramo más cercano (≤ 25 m) → `data/campo/tramos_revisados.csv` (cobertura ≥ 50 % o tramo < 30 m) y eventos
  `origen='phyphox'`. Protocolo para Pipe en `analysis/README.md`.

## 10. Modelo de riesgo (plan B incluido)
- Variables por tramo (`risk_model/variables.py`): tipo de vía, superficie, longitud, pendiente, lluvia 30 días y máxima (IDW),
  huecos vecinos ≤ 300 m **en otros tramos**, siniestros ≤ 200 m, rugosidad y profundidad, barrio y sector.
- Etiquetas: 1 si alguna fuente vio un hueco; 0 si el tramo fue revisado sin huecos; fuentes `alcaldia`, `recorrido`,
  `visita`, `nodo`, `bot` (`variables_tramo.fuente_etiqueta`). Archivos: `data/alcaldia/huecos.csv` (lat, lon),
  `data/campo/tramos_revisados*.csv` (id_tramo, tiene_hueco). Eventos `simulado` se ignoran salvo `--incluir-simulados`.
- `python -m risk_model.modelo --fuente auto|alcaldia|planb|todas --guardar --lista-campo`: logística y bosque,
  **GroupKFold por barrio** (AUC espacial, meta ≥ 0,70) y AUC con pliegues al azar como comparación; requiere ≥ 30
  etiquetados, ≥ 5 por clase y ≥ 3 barrios. `--lista-campo` = top-10 de riesgo no reportados vs. 10 al azar.
- `--demo-sintetico` solo prueba el flujo (versión `DEMO-SINTETICO`, aviso rojo en tablero y mapa).

## 10b. Dataset de fotos del celular (`dataset/`, desde el 3-nov)
- **Protocolo:** `docs/protocolo_fotos.md`. 9 clases: `hueco, resalto, grieta, parche, tapa, obstaculo, linea_carril,
  paso_peatonal, via_buena`; severidad leve/media/alta solo en daños; 4–5 fotos por punto (contexto, frente, lado, cenital
  con tarjeta, termohigrómetro). Drive → `data/raw/fotos/AAAA-MM-DD_nombre/` (nunca WhatsApp: borra el EXIF).
- **Esquema** (`dataset/comun.py`, `COLUMNAS`): id, archivo, autor, fecha, hora, momento_dia, lat, lon, id_tramo, barrio,
  tipo_via, superficie, clase, severidad, angulo, distancia_m, luz, superficie_mojada, temperatura, humedad, lux, fuente_clima,
  lluvia_ideam, notas, largo_regla_cm, ancho_regla_cm (las 2 últimas opcionales). id = SHA-1[:12] del archivo.
- **Ingesta** (`dataset.ingesta`): EXIF (hora local UTC-5 si no trae zona), tramo OSM ≤ 30 m, barrio, tipo de vía sugerido,
  clima (termohigrómetro > nodo ± 30 min > Open-Meteo), lluvia IDEAM, difuminado (Haar; caras exigen ≥ 15 % de piel YCrCb
  porque sin eso se borraban las cebras), copia sin EXIF ≤ 2048 px a `data/procesado/fotos/`, `calidad.csv` y
  `reporte_calidad.md`. Nunca pisa lo etiquetado. Notas con `EXCLUIR` = fuera del modelo.
- **Etiquetador** (`dataset.etiquetador`): http.server de la biblioteca estándar en 127.0.0.1:8765, teclas 1–9/QWE/ASDF/ZXCV/M.
- **Escala** (`dataset.escala`): ArUco DICT_4X4_50 de **80 mm** (`tarjeta_aruco.py`), homografía de 4 puntos, vista cenital
  a 1 mm/px, área = mancha oscura (Otsu ≤ 65 % de la mediana) que no toque el borde. Aproximada; se valida con regla.
- **Planilla** (`dataset/planilla.py`): CSV de Google Sheets (N.º, Fecha, Hora, Clase, Severidad, Tipo de vía = superficie,
  ¿Mojado?, Luz, Clima, Barrio/calle, Fotógrafo, N.º fotos, Notas) unido por hora ± 5 min y sitio; solo llena celdas vacías.
- **Modelo** (`dataset.modelo`, tf_keras): MobileNetV3-Small o MobileNetV2 (`--comparar` ambas), 224 px, **por sitio**,
  aumentos para Tunja en tf.data, `--preentrenar` con recortes externos, TFLite float32 / int8 PTQ (200 y 1000 aumentadas) /
  int8 QAT (solo V2), Grad-CAM, latencia. Salidas en `dataset/salidas/<versión>/` (`ultimo.txt`, `info.json`).
- **Uso del modelo:** `web/clasificador/` (tfjs-tflite en el navegador; `preparar.py --servir`) y el bot
  (`dataset/clasificar.py` con LiteRT).
- **Sintético** (`dataset.sintetico`, `--sintetico` en todo): `data/raw/fotos_sintetico` → `data/procesado_sintetico`, nunca
  se mezcla ni se reporta. Prueba del 5-nov: V3 int8 cae (0,90 → 0,57–0,70, núcleos de referencia ~100 ms); V2 int8 PTQ 0,93.
- **Validar campo:** `dataset\.venv\Scripts\python -m herramientas.validar_campo` antes de la ingesta y de `etl.recorridos`.

## 11. Entorno de desarrollo (PC de Andrés, Windows 11)
| Herramienta | Dónde / cómo |
|---|---|
| Python 3.11 | `py -3.11`. Venvs: `etl\.venv` (ETL **y** `risk_model`), `analysis\.venv` (torch CPU, emlearn), `bot\.venv` (+ LiteRT), `dataset\.venv` (OpenCV **< 5**, scipy, pytest) y **`%USERPROFILE%\.venvs\vv-modelo`** (TensorFlow **2.20**, tf_keras, tfmot: no cabe en la ruta del repo sin rutas largas). Versiones fijadas el 5-nov (pandas 3.0.0, scikit-learn 1.7.2, TF 2.20.0) porque Smart App Control bloqueaba las nuevas; Andrés lo desactivó, pero las fijadas son las probadas |
| Pruebas | `dataset\.venv\Scripts\python -m pytest` (desde `via-viva/`) |
| PlatformIO | `%USERPROFILE%\.platformio\penv\Scripts\pio.exe` (no está en el PATH) |
| MiKTeX 25.12 | Instalado por usuario con winget; `pdflatex main`, `bibtex main`, `pdflatex main` ×2 en `report/`. Incluye `pdftoppm` |
| Java / NetBeans | JDK 25 (`C:\Program Files\Java\jdk-25.0.4.1`), NetBeans 25 con Ant en `C:\Program Files\NetBeans-25\netbeans\extide\ant`; para compilar por consola pasar `-Dlibs.CopyLibs.classpath=...\java\ant\extra\org-netbeans-modules-java-j2seproject-copylibstask.jar` |
| Microsoft Word | Instalado: sirve para revisar `.docx` exportándolos a PDF por COM |
| GitHub | Organización `via-viva-usta`, repo **privado** `via-viva`. **Cuenta correcta: `andresscardens`.** En este PC `gh` también tiene `acstromia` (cuenta de trabajo) y a veces queda activa: verificar con `gh auth status`; para cambiar: `gh auth switch --user andresscardens`, o en un solo comando: `GH_TOKEN=$(gh auth token --user andresscardens) gh ...`. `git push` ya funciona con las credenciales guardadas |

**Trampas conocidas (para Claude):**
- En la herramienta Bash, los *heredoc* con barras invertidas (`\\n`, regex, LaTeX) se dañan: escribir esos scripts con la
  herramienta Write en el scratchpad y ejecutarlos.
- La consola de Windows imprime mal UTF-8: usar `PYTHONIOENCODING=utf-8`.
- Overpass (OSM) a veces responde 502/504: `etl.osm_tunja` reintenta y usa espejos; luego usa la caché `data/osm/cache`.
- pandas 3: `groupby().apply` descarta las columnas de agrupación; en Windows sin rutas largas, JupyterLab no se instala.
- El panel del navegador abre archivos locales como copia estática (no carga `datos.js`): servir `web/` con
  `python -m http.server` para probar el mapa.
- Descargar ejecutables (p. ej. Tectonic) puede ser bloqueado por los permisos de la sesión; pedirlo al usuario.
- Keras 3: `compile(optimizer=..., loss=..., metrics=...)` **con nombre** (el 3.er posicional es `loss_weights`). Para TFLite se
  exporta un modelo de inferencia SIN capas de aumento (sus operaciones aleatorias no existen en TFLite).
- PlatformIO no busca librerías desde `../include`: un programa de `pruebas/` que use `ambiente.h` debe incluir `<Wire.h>`.
- Si `pio.exe` falla (Control de aplicaciones), usar `%USERPROFILE%\.platformio\penv\Scripts\python.exe -m platformio`.
- tfmot no cuantiza modelos anidados ni las hard-swish de MobileNetV3: la QAT se hace con MobileNetV2 en un modelo plano.
- tfjs-core solo (sin `@tensorflow/tfjs` completo) no trae los métodos encadenados: usar `tf.expandDims(x)`, no `x.expandDims()`.

## 12. Equipo
| Persona | GitHub | Área principal | Apoyo |
|---|---|---|---|
| Andrés Cárdenas | `andresscardens` (admin de la organización) | C. Datos y plataforma · D. Gestión y documento | B |
| Dany Cipamocha | `dany286-ri` (member; **read** en el repo: issue #17) | A. Hardware y firmware | C |
| Juan Felipe García ("Pipe") | `juanfelipegarciacarvajal444-rgb` (owner) | B. Señales e IA; phyphox (iPhone 17) | — |
| Juan Diego Anzola | `Juandi-1` (owner) | Fotos (iPhone 15), informe en Overleaf, póster, video, pitch | A, D |

Roles recomendados (auditoría del 5-nov, `docs/ESTADO.md`): un solo owner (Andrés) y los demás Member con Write.

Andrés opera Claude Code; los demás prueban, aportan datos y revisan por Pull Requests.

## 13. Calendario (entrega 13-nov-2026)
| Fase | Fechas | Contenido |
|---|---|---|
| 1 | 26–30 oct | Repo, ETL/OSM, scraping, base, diagramas — **hecha** |
| 2 | 28 oct – 2 nov | Firmware sin hardware, bot, mapa web, tablero — **hecha (compila)** |
| 3 | 2–6 nov | Hardware y recorridos: montaje, pruebas por sensor (+ ambiente), phyphox, E1–E4; tarjetas ArUco y Drive |
| 3b | 5–9 nov | **Salidas de fotos** (≥ 500) y recorridos phyphox; validación + ingesta diaria |
| 4b | 8–11 nov | Etiquetado (Pipe y Juan Diego), escala validada, modelo de fotos e int8 |
| 4 | 3–8 nov | Detector int8 y modelo de riesgo con datos reales |
| 5 | 6–9 nov | Validación en campo (top-10 vs. azar); **9-nov = fecha límite del plan B** |
| 6 | 9–13 nov | Tablero y mapa con datos reales, informe, póster, video, pitch |
