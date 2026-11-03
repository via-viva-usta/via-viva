# CLAUDE.md — VÍA VIVA (contexto para Claude Code)

Lee este archivo completo antes de trabajar. Es la fuente de verdad técnica del repositorio.
**Para continuar el trabajo, lee después `docs/ESTADO.md`** (qué está hecho, qué está probado y qué falta por persona)
y los issues abiertos de GitHub. Con esos dos archivos un chat nuevo puede seguir sin más contexto.

Última actualización: **3-nov-2026**. Entrega final: **13-nov-2026**.

## 1. Qué es el proyecto
VÍA VIVA es el Proyecto Integrador 2026-2 (2.º semestre, Ingeniería de Datos e IA, Universidad Santo Tomás, Seccional Tunja).
Detecta, mapea y **predice** huecos, resaltos, impactos y obstáculos en las vías de Tunja (Colombia).

- **Nodo en el carro (IA en el borde):** ESP32 normal (WROOM-32) + acelerómetro ADXL345 (SPI) + MPU-6050 (I2C) +
  láser VL53L0X (I2C) + GPS NEO-6M (UART) + microSD (SPI) + pulsador. Detector por umbrales + clasificador int8 en el nodo;
  maniobras con el giroscopio; página web propia (punto de acceso Wi-Fi) para etiquetar. Una ESP32-CAM (OV2640) toma foto
  solo cuando hay evento y la difumina.
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
| 2-nov | ESP32-CAM se programa con adaptador USB-TTL **CP2102** (sin base MB) |
| 2-nov | Presupuesto aproximado **330.000 COP** (antes 342.400 con la S3) |
| 2-nov | Atención al ciudadano = **bot de Telegram + mapa web estático, sin backend**; para la demo el bot corre en el portátil |
| 2-nov | Base de datos **SQLite** detrás de la capa de acceso `db/acceso.py` (lista para migrar a PostgreSQL/PostGIS) |
| 2-nov | Datos: recorridos normales en carro a **máx. 30 km/h**; primero celular (**phyphox**), luego el nodo |
| 2-nov | **Ajustes del docente de Arquitectura:** (a) detector por umbrales como línea base y pre-etiquetado; (b) clases de maniobra con el giroscopio (giro izq./der., frenada brusca); (c) servidor web en el ESP32 con botones de etiquetado, Wi-Fi en núcleo 0 y adquisición en núcleo 1 |
| 2-nov | **Plan B de etiquetas del modelo de riesgo:** si la Alcaldía no entrega datos antes del **9-nov**, se entrena con tramos revisados en recorridos (+ visitas) + reportes del bot. Cada corrida registra la fuente (`--fuente auto`) |
| 2-nov | Trabajo en equipo por **ramas y Pull Requests** (`CONTRIBUTING.md`); Andrés revisa y fusiona |
| 2-nov | E2 = pesos en flash vs. SRAM; E3 = float32 vs. int8 (sin PSRAM ni instrucciones vectoriales en la ESP32 normal) |
| 3-nov | Informe IEEE (`report/`) se compila con **MiKTeX** en el PC de Andrés; `main.pdf` no se sube a Git |
| 3-nov | Cuenta de GitHub del proyecto: **`andresscardens`** (ver sección 11) |

Documentos de referencia: `docs/03_VIA_VIVA_desarrollo.md` (diseño; con nota del cambio de placa), `docs/propuesta/`
(propuesta entregada, con ESP32-S3: **no se modifica**), `docs/diagramas/` (Mermaid), `docs/montaje.md`,
`docs/experimentos.md`, `docs/demo.md`, `docs/poster.md`, `docs/ESTADO.md`.

## 3. Materias que el código debe evidenciar
| Materia | Qué debe quedar demostrable | Dónde está |
|---|---|---|
| Sistemas de Adquisición (SADP) | Muestreo justificado (espectro/Nyquist), filtros, sincronía GPS, características, métricas de detección | `analysis/`, `firmware/.../caracteristicas.h` |
| Arquitectura del Computador | SPI/I2C/UART, FIFO + interrupción + DMA ping-pong, doble núcleo FreeRTOS, RAM/flash, latencia, consumo (E1–E4) | `firmware/nodo-sensores/`, `docs/experimentos.md` |
| Estructuras de Datos | Búfer circular y colas (nodo), tabla hash + geohash, grafo con BFS, heap, análisis de complejidad | `dashboard-java/`, `firmware/.../bufer_circular.h`, `etl/geohash.py` |
| Requisitos extra | ETL, web scraping, IA ligera, demo | `etl/`, `analysis/`, `docs/demo.md` |

Pendiente del diseño original de Estructuras: bitácora por fechas con `TreeMap` y "peligros" agrupados (cuando haya eventos).

## 4. Estructura del repositorio
```
via-viva/
├── CLAUDE.md · README.md · CONTRIBUTING.md · .gitignore · .gitattributes · .env.example
├── docs/            diseño, propuesta, diagramas Mermaid, ESTADO, montaje, experimentos, demo, póster
├── firmware/
│   ├── nodo-sensores/   PlatformIO esp32dev: src/ (módulos), include/ (pines.h, config.h, secretos.example.h),
│   │                    pruebas/ (un programa por sensor), wokwi/ (simulación), diagram.json + wokwi.toml
│   └── nodo-camara/     PlatformIO esp32cam
├── db/              schema.sql (8 tablas), acceso.py (capa de acceso), reconstruir.ps1
├── etl/             osm_tunja, barrios_tunja, elevacion, scraping/ (clima IDEAM, noticias), recorridos, recorrido_sintetico
├── analysis/        senales.py, detector_umbral.py, modelo_cnn.py, entrenar_detector.py, experimentos.py, notebook
├── risk_model/      variables.py (tabla de variables por tramo), modelo.py (logística y bosque, plan B)
├── bot/             bot.py, reportes.py, cambiar_estado.py
├── web/             index.html (Leaflet) + exportar.py → datos.js (generado, ignorado)
├── dashboard-java/  NetBeans Ant, Java 21: estructuras/ (TablaHash, MonticuloMax, GrafoCalles, IndiceGeohash)
├── report/          main.tex (IEEE), referencias.bib, figuras/generar.py, tablas/ (generadas por experimentos.py)
└── data/            solo README y muestras; raw/, alcaldia/, osm/, campo/, fotos_bot/ y la base .db están ignorados
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
| I2C SDA / SCL | 21 / 22 | MPU-6050 (0x68) y VL53L0X (0x29), 400 kHz |
| GPS NEO-6M (TX del GPS → RX / RX ← TX) | 16 / 17 | UART2, 9600 baud |
| Enlace ESP32-CAM TX / RX | 25 / 35 | UART1, 115200 baud |
| Pulsador | 26 | INPUT_PULLUP, a GND, antirrebote 250 ms |
| LED | 33 | salida |

**ESP32-CAM (AI-Thinker):** RX = GPIO 13 ← GPIO 25 del nodo; TX = GPIO 14 → GPIO 35 del nodo; 1 kΩ en serie; 5 V estables
con condensador de 470–1000 µF. Programación con CP2102: 5V–5V, GND–GND, TXD→U0R (GPIO 3), RXD→U0T (GPIO 1), GPIO 0 a GND
al subir, quitarlo y RST para correr. Protocolo: `PING`→`PONG`; `FOTO,<id>,<hora>`→`OK,<id>,<bytes>` o `ERR,<id>,<código>`.
Hoy difumina **todo** el cuadro (gris 320×240); falta el difuminado selectivo y enviar la miniatura.

**Montaje:** MPU-6050 con **X hacia adelante y Z hacia arriba** (si no, cambiar `EJE_*`/`SIGNO_*` en `config.h`); ADXL345 y
MPU rígidos a la baquela; detalles, orden de prueba y errores típicos en `docs/montaje.md`.

## 7. Firmware del nodo (`firmware/nodo-sensores`)
- **Tareas:** núcleo 1 = `tareaAdquisicion` (prioridad 20) y `tareaProcesamiento` (10); núcleo 0 = Wi-Fi + web, GPS, I2C +
  maniobras, cámara, microSD, estadísticas. `loop()` se elimina para medir el ocio del núcleo 1.
- **Adquisición:** ADXL345 a 200 Hz, ±16 g resolución completa (3,9 mg/LSB), FIFO *stream* con **watermark 31** (el campo tiene
  5 bits → interrupción cada 155 ms), lote por DMA a 1,5 MHz (≤ 1,6 MHz no necesita pausa entre lecturas de la FIFO),
  búfer **ping-pong** de 2 mitades con semáforos; `bloques_perdidos` si el procesamiento se atrasa.
- **Modo de adquisición (E1) por entorno:** `esp32dev` = FIFO+DMA (normal), `e1_polling`, `e1_int_muestra`.
- **Detector por umbrales** (`src/detector_umbral.h`, igual a `analysis/detector_umbral.py`): evento si velocidad GPS >
  **5 km/h** y el pico a pico de la aceleración vertical en **50 ms** > **6 ×** RMS de fondo (promedio exponencial, τ = **2 s**,
  usando el valor anterior) y > **0,30 g**, con **1 s** refractario y 2 s de calentamiento. Señal = \|a\| − 1 g. **Sin calibrar.**
- **Maniobras** (`src/maniobras.h`): giro si \|ω vertical filtrada (τ 0,25 s)\| > **15 °/s** durante **1 s** con velocidad > 5 km/h
  (positivo = izquierda); frenada si aceleración longitudinal < −**0,30 g** durante **0,5 s** o caída GPS > **2,5 m/s²**. Un golpe
  durante una maniobra se atribuye a la maniobra y no se pide foto.
- **Clase del evento:** hoy **provisional por reglas** (`clasificarProvisional`); el modelo int8 existe pero está entrenado con
  datos SINTÉTICOS (`MODELO_SINTETICO 1` en `src/modelo_cnn.h`): sirve para medir latencia, no para clasificar.
- **Página web** (`src/servidor_web.cpp`): red `VIA-VIVA-NODO`, http://192.168.4.1, botones Hueco/Resalto/Otro, "modo mesa"
  (ignora la velocidad para probar sin carro), estado de sensores y modo E1.
- **microSD por sesión:** `crudo_NNN.csv` (t_us, cuentas), `eventos_NNN.csv`, `gps_NNN.csv`, `etiquetas_NNN.csv`
  (tipo, origen web/botón), `fotos_NNN.csv`, `exp_NNN.csv` (experimentos).
- **Experimentos:** E1 cada 5 s; E2/E3/E4 y memoria **al arrancar** antes de crear tareas (`src/experimentos.cpp`).
- Tamaño (esp32dev): RAM estática 60 156 B (18,4 %), flash 916 145 B (46,6 %), partición `min_spiffs.csv`.

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

## 11. Entorno de desarrollo (PC de Andrés, Windows 11)
| Herramienta | Dónde / cómo |
|---|---|
| Python 3.11 | `py -3.11`. Venvs: `etl\.venv` (ETL **y** `risk_model`), `analysis\.venv` (incluye torch CPU y emlearn), `bot\.venv` |
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

## 12. Equipo
| Persona | GitHub | Área principal | Apoyo |
|---|---|---|---|
| Andrés Cárdenas | `andresscardens` (admin de la organización) | C. Datos y plataforma · D. Gestión y documento | B |
| Dany Cipamocha | `dany286-ri` (hoy solo **lectura** en el repo: issue #17) | A. Hardware y firmware | C |
| Juan Felipe García ("Pipe") | no está en la organización | B. Señales e IA | — |
| Juan Diego Anzola | probablemente `Juandi-1` (miembro desde el 3-nov; confirmar) | Apoyo A y D (póster, video, pitch) | A, D |

Andrés opera Claude Code; los demás prueban, aportan datos y revisan por Pull Requests.

## 13. Calendario (entrega 13-nov-2026)
| Fase | Fechas | Contenido |
|---|---|---|
| 1 | 26–30 oct | Repo, ETL/OSM, scraping, base, diagramas — **hecha** |
| 2 | 28 oct – 2 nov | Firmware sin hardware, bot, mapa web, tablero — **hecha (compila)** |
| 3 | 2–6 nov | Hardware y recorridos: montaje, pruebas por sensor, phyphox, E1–E4 |
| 4 | 3–8 nov | Detector int8 y modelo de riesgo con datos reales |
| 5 | 6–9 nov | Validación en campo (top-10 vs. azar); **9-nov = fecha límite del plan B** |
| 6 | 9–13 nov | Tablero y mapa con datos reales, informe, póster, video, pitch |
