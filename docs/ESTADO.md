# Estado de VÍA VIVA

Última actualización: **11-nov-2026**. Entrega final: **13-nov-2026**. Decisiones y datos técnicos: `CLAUDE.md`.
Tareas: issues de GitHub (`via-viva-usta/via-viva`). Flujo de trabajo: `CONTRIBUTING.md`.

## 12-nov: app v1 (rama `ac/app-v1`, PR abierto)

App local con la marca de Dany, mapa MapLibre/OpenFreeMap que funciona sin internet, ejemplo que recorre Tunja,
panel de conexión, cámara en vivo e icono de escritorio. **Probado en el PC de AC:** instalación limpia (clon nuevo),
icono → ventana propia → grabar → cerrar guarda la sesión; mapa con y sin internet; panel con el simulador de phyphox;
grabación de video con una cámara SINTÉTICA en Edge. **Sin probar:** webcam real, iPhone B por HTTPS, Mac, Docker y la
Pi con esta versión. Detalle en `CHANGELOG.md`.

## Resumen al 11-nov

- **Nodo:** Raspberry Pi 4 (la ESP32 salió el 9-nov; `firmware/` queda como historia). Fase 1 = umbrales; fase 2 =
  TFLite solo cuando haya marcas reales suficientes.
- **Software:** una sola app (`viaviva/`): Campo → Sesiones → Importar video → Revisión → Dataset → Demo, más el tablero
  local y el sitio en línea (portada + `tablero.html`). Funciona **en el PC**, probado con el **simulador** de phyphox,
  reproducciones de los 3 recorridos reales y datos SINTÉTICOS.
- **Sin probar en su entorno real:** phyphox con el iPhone real, video real del iPhone B, la Pi (instalación, sensores,
  servicio, R7), Supabase/Netlify en producción y marcas reales para calibrar.

## Resumen histórico (7-nov; lo de la ESP32 ya no aplica)

0. **7-nov — primeros datos REALES:** 3 recorridos de phyphox del iPhone de Pipe (01: 5,2 min · 02: 7,2 min · 03: 13,6 min),
   copiados a `data/raw/phyphox/2026-11-07_0N_pipe.zip` (ignorada por Git). Pasan el validador: **100 Hz, 0 cortes de
   muestreo, GPS ~99 %**. Faltan sus etiquetas. Para leerlos hubo que arreglar el lector (iOS escribe `X (m/s^2)`).
   Nueva **captura en vivo** por el acceso remoto de phyphox (plan A de etiquetado; el cronómetro queda como plan B).

1. **Todo el software existe, compila y tiene pruebas** (68 pytest al 7-nov; GitHub Actions para Python y firmware), pero
   **nada se ha probado en hardware** (el ESP32 DevKit V1, DHT22 y BH1750 están por llegar) y **no hay datos reales**:
   salvo los 3 recorridos de phyphox del 7-nov (sin etiquetas).
2. Todo lo que tiene números (detector, modelo de riesgo, modelo de fotos, escala) se probó **solo con datos SINTÉTICOS**
   marcados; no son resultados. En el informe siguen como `[PENDIENTE]`.
3. Campo listo: protocolo de fotos (iPhone 15 de Juan Diego), planilla de campo, cronómetro por vueltas para phyphox
   (iPhone 17 de Pipe, ~100 Hz) con su conversor, y **validador** que dice "bien / corregir" antes de procesar.
4. Demo lista en un comando (`.\iniciar.ps1`, con `-Reproducir` la Pi reproduce un recorrido real) con base DEMO
   separada; el clasificador corre en el navegador del celular (probado en el PC, falta el iPhone). Bot pospuesto.
5. Lo que destraba todo: **primeras salidas de campo** (fotos + phyphox) y **montar la Raspberry Pi** (nodo central desde
   el 7-nov) con los sensores, después de la rama de Dany.

## Fases

| # | Fase | Fechas | Estado |
|---|---|---|---|
| 1 | Repositorio, datos y modelado | 26–30 oct | ✅ Hecha |
| 2 | Firmware sin hardware, bot, mapa web, tablero | 28 oct – 2 nov | ✅ Hecha |
| 3 | Hardware y recorridos (montaje, pruebas por sensor, phyphox, E1–E4) | 2–9 nov | 🟡 3 recorridos de phyphox recibidos, sin etiquetas; hardware por llegar |
| 3b | Salidas de fotos (≥ 500) + planilla + validación | 5–9 nov | 🟡 Todo listo; **0 fotos** |
| 4 | Detector int8 y modelo de riesgo con datos reales | 6–9 nov | 🟡 Cadenas listas (sintéticos); faltan datos |
| 4b | Etiquetado, escala validada, modelo de fotos (int8), clasificador en el iPhone | 8–11 nov | 🟡 Cadena completa con sintéticos; faltan fotos |
| 5 | Validación en campo (top-10 vs. azar); **9-nov = fecha límite del plan B** | 8–10 nov | ⬜ Depende de 3 y 4 |
| 6 | Entrega: datos reales en tablero y mapa, informe (Overleaf), póster, video, pitch | 9–13 nov | 🟡 Demo y texto del informe listos con [PENDIENTE] |

## Hecho el 11-nov: video del iPhone y revisión de pantallas (86 pruebas pasaron, 1 omitida; Ruff limpio)

| Qué | Estado |
|---|---|
| Importar video: detecta el códec; si es HEVC o el navegador no lo reproduce, lo avisa y ofrece «Convertir a H.264» con ffmpeg (opcional, en segundo plano, conserva el original y el desfase) | pytest con ffmpeg simulado + navegador con un video sintético que Chrome no reproduce. **ffmpeg no está instalado en el PC**; falta un .mov HEVC real |
| Navegación de la app (Campo, Sesiones, Revisión, Dataset, Tablero, Demo, Entrar, `/marcar`, `/sync`) | Cada ruta abre su pantalla (PC, datos SINTÉTICOS); Campo y Revisión sin desbordes a 375 px |

## Hecho el 10-nov: un solo sistema (MVP para la presentación)

| Qué | Estado |
|---|---|
| Conexión phyphox (puerto 80/8080, buffers desde `/config`, URL en `.env`, minuto quieto con 5 km/h) | Probado con el simulador; **falta el iPhone real** |
| Campo, Sesiones, Importar video, Revisión, Dataset, Demo, Tablero con los temas A/B | 85 pruebas pasaron, 1 omitida; Ruff limpio. Revisión visual hecha el 11-nov (arriba) |
| Sincronía de video por destello | Probada con un video sintético; **falta un video real del iPhone B** (HEVC: ver 11-nov) |
| Dataset y umbrales desde la app | Funciona; **sin marcas reales aún**, así que las cifras no son resultados |
| Tablero en línea | Portada + `tablero.html` de `main` (PR #30) con la marca de Dany (decisión del 11-nov; el tema B queda para el tablero local y los reportes); falta despliegue y la evidencia de video por evento |

## Hecho el 10-nov: cierre del software (rama `ac/cierre-software`, 85 pruebas pasaron, 1 omitida, Ruff limpio)

| Fase | Terminado | Parcial / pendiente (por qué) |
|---|---|---|
| **A** captura PC + phyphox | `viaviva doctor`, `capture` con reconexión sin pérdida, sesión + RESUMEN, marcas 1–7/U con retardo, `/marcar` con PIN, `/sync` con destello, `--replay` (directo y por HTTP), `SALIDA_DE_CAMPO.cmd`, `README_SALIDA.md`. Probado de punta a punta con el simulador y los 3 exports reales | Falta la prueba con el iPhone real y el Firewall de Windows (lo acepta AC la primera vez) |
| **B** detector y dataset | Detector YAML (orientación libre), evaluación y calibración por salida, dataset de ventanas, esqueleto TFLite | **No hay marcas reales**: nada calibrado ni evaluado con datos reales. Los 3 recorridos dan 4 / 11 / 28 disparos sin calibrar |
| **C** Raspberry Pi | Pines del manual v3, sensores opcionales, gpio-shutdown, instalador y servicio | **Sin probar en hardware** (pruebas con controladores falsos) |
| **D** tablero en línea | Esquema Supabase con RLS por rol, sincronización de huecos y cambios en línea, sitio estático probado en modo DEMO | **Sin desplegar**: falta que AC cree el proyecto de Supabase e inicie sesión en Netlify (`docs/NUBE.md`) |
| **E** R7, calidad, docs | R7 en el PC (n = 200), ruff + cobertura en la CI, scraping revisado, docs nuevas | R7 en la Pi y consumo con el tester: pendientes |

Hallazgo con datos reales: en el recorrido 02 el GPS marca 3–5 km/h durante el "minuto quieto" (el acelerómetro está
quieto); el RESUMEN nuevo lo cuenta como NO quieto. El 7-nov `validar_campo` lo daba por bueno (solo miraba el acelerómetro).

## Hecho el 7-nov (noche): Raspberry Pi 4 = nodo central y aplicativo

> Registro histórico: las rutas `pi/…` de esta sección hoy están en `viaviva/` (10-nov) y la ESP32 salió el 9-nov.

Decisión del 7-nov: el docente de Arquitectura consideró insuficiente el ESP32; la Pi pasa a nodo central y el ESP32 a
línea base de R7. Todo se probó **en el PC** (68 pytest y reproduciendo el recorrido 03 de Pipe); **nada en la Pi todavía**.

| Qué | Dónde | Probado |
|---|---|---|
| Sensores directo a la Pi (ADXL345 SPI con FIFO + interrupción, MPU-6050, VL53L0X, BH1750, GPS NMEA, DHT22 tolerante, pulsador, LED) | `pi/sensores.py`, `pi/fuentes.py` | Parser NMEA con pytest; **controladores sin placa** [VALIDAR EN PLACA] |
| Núcleo: detector igual al de phyphox/ESP32, grabación en formato phyphox, hora del GPS | `pi/nucleo.py` | pytest + recorrido real 03 reproducido a 20×: 38 eventos ajustados a su tramo |
| Captura para celular o tablet fija (botones grandes, señal, GPS, sensores, apagado seguro) | `pi/web/captura.html` | Navegador del PC (escritorio y 375 px); **falta el celular y la tablet reales** |
| Tablero en vivo: capas de huecos (por estado) y de riesgo por tramo, top-10, orden de atención, reportes, historial | `pi/web/tablero.html`, `pi/almacen.py` | Navegador del PC con base DEMO; captura en `docs/img/tablero_pi.png` |
| Huecos: detecciones ≤ 10 m, detectado → verificado → reparado / descartado, reapertura | `pi/almacen.py` | pytest |
| Roles: editor (4), alcaldia y docente de lectura; sesiones; límite de intentos | `pi/usuarios.py` | pytest. **Faltan crear los usuarios** (cada quien su clave) |
| Exportar PDF top-10 con mapa, Excel de 3 hojas, CSV; importar reparaciones con validación | `pi/exportar.py` | pytest + descarga desde el tablero |
| Sincronización: cola con reintentos, solo eventos y riesgo, lista blanca; esquema con RLS | `pi/sincronizacion.py`, `pi/supabase_esquema.sql` | pytest con un servidor falso. **No hay proyecto de Supabase creado** |
| Instalación, punto de acceso WiFi, apagado seguro, systemd | `pi/instalar.sh`, `pi/sistemas/` | **Sin probar** (no hay Pi) |
| R7: registro cada 10 s (latencias, CPU, temp., RAM, bajo voltaje), consumo, tabla Pi vs. ESP32 vs. celular | `pi/sistema.py`, `pi/r7/` | Tabla genera [PENDIENTE] en todo: falta medir en la Pi |
| Bot de Telegram pospuesto; `futuro/pi` → `pi/` | `futuro/bot/`, `docs/archivo/LEEME.md` | Prueba del bot sigue en verde |

**Falta (Pi):** confirmar pines con la rama de Dany · especificaciones (RAM, fuente, microSD) · instalar y crear
usuarios · probar sensores uno por uno · medir R7 y consumo con el tester USB · probar captura en el celular/tablet
en el carro · si se quiere la nube: crear el proyecto de Supabase, pegar `pi/supabase_esquema.sql` y poner las claves
en el `.env` de la Pi.

## Hecho el 7-nov (bloques 3 y 4: R5, R7, R3, Pi)

| Requisito | Qué | Evidencia |
|---|---|---|
| **R5 scraping** | `etl.scraping.diario`: IDEAM incremental (`--dias 3`, se amplía solo si hubo días sin correr) + noticias; log JSON por corrida; frescura (avisa si el último dato tiene > 3 días). **Tarea diaria registrada** en el PC de Andrés ("VIA VIVA scraping diario", 06:30, `herramientas/programar_scraping.ps1`) | `data/logs/scraping_diario.jsonl`; `python -m etl.scraping.diario --resumen`. 1.ª corrida: 15 filas nuevas de 5 estaciones; huecos 2–3 nov rellenados; lluvia al día hasta el 6-nov |
| **R7 rigor** | Welford en `medir()` del firmware (media ± desv., N = 200/500, sin RAM extra); latencia del modelo en el celular (100 inferencias) con registro en el PC; tabla de memoria en `docs/experimentos.md` | Compila (flash 944 585 B, 48,0 %). Control en el PC: 10,73 ± 0,26 ms (navegador), 5,16 ± 0,34 ms (LiteRT). **iPhone y placa: pendientes** |
| **R3 int8** | `dataset.modelo` agrega la tabla de **F1 por clase** de float32 vs. PTQ vs. QAT y la peor caída por clase (división por sitio sin cambios) | Espera fotos reales |
| Reproducibilidad | `entornos/*.txt` (pip freeze de los 5 venvs) | `entornos/LEEME.md` |
| Seguridad | `herramientas/buscar_secretos.py`: 74 commits revisados, **sin secretos**; `.env`, `secretos.h` y `kaggle.json` nunca se subieron | 2 pruebas pytest |
| Pi 4 (futuro) | Servidor 24/7 (bot + scraping con systemd) y benchmark de la CNN int8; **MobileNetV2 int8 no cabe en el ESP32** (activaciones ≥ 1 470 KB vs. ~300 KB libres) | `futuro/pi/`; especificaciones y medición en la placa pendientes |

## Hecho el 7-nov (mañana)

| Qué | Dónde |
|---|---|
| Lector de phyphox para **iOS** (columnas `X (m/s^2)`, `X (rad/s)`); validación de los 3 recorridos reales | `analysis/senales.py`, `data/raw/validacion_campo.md` (local) |
| **Captura en vivo** desde phyphox: CSV en formato iOS, reconexión sin pérdida, etiquetas por teclado (H R G T O I P Q), vista en vivo (velocidad, aceleración, mapa, eventos del detector), modo reproducir/simular | `herramientas/captura_phyphox_remoto.py`, `herramientas/vista_en_vivo.html` |
| README con 3 pasos y captura del tablero; **un solo `iniciar.ps1`** (con `-Phyphox` y `-Reproducir`); obsoleto movido a `docs/archivo/` (lista en `LEEME.md`); `.gitignore` cubre `data/` | raíz, `docs/archivo/`, `docs/img/` |
| Cambios de la revisión técnica validados: DMA del ADXL345 de 8 bytes (compilan los 3 entornos) y extracción segura del ZIP (9 pruebas) | `firmware/nodo-sensores/src/adxl345.*`, `dataset/externos.py` |

## Hecho el 5-nov (y dónde está)

| Bloque | Qué | Dónde |
|---|---|---|
| A1 | Auditoría: roles de GitHub (abajo), issues con usuarios reales y fechas, textos alineados (DHT22, sin S3/CAM) | issues, `CLAUDE.md`, `docs/` |
| A2 | `tipo_via` automático desde OSM; columna nueva **`superficie`**; **planilla de campo** (CSV de Google Sheets) unida a las fotos por hora (± 5 min) y sitio; rutas de Drive reales | `dataset/planilla.py`, `dataset/ingesta.py`, `docs/protocolo_fotos.md`, `analysis/README.md` |
| A3 | **Conversor de vueltas** del cronómetro del iPhone → `_etiquetas.csv`; paradas = carro detenido (el detector no busca ahí) | `analysis/vueltas_a_etiquetas.py`, `etl/recorridos.py` |
| A4 | **Validador de campo**: phyphox (columnas, Hz, cortes, GPS, quieto 1 min), fotos (EXIF, GPS, HEIC, nitidez, ArUco), planilla | `herramientas/validar_campo.py` |
| B1 | Revisión de datasets externos: Kaggle usable (DbCL), Hugging Face **descartado** (licencia no documentada) | `docs/datasets_externos.md`, `dataset/externos.py` |
| B2 | CNN con aumentos para Tunja, pre-entrenamiento externo opcional, **PTQ vs. QAT**, Grad-CAM, latencia, comparación MobileNetV3 vs. V2 | `dataset/modelo.py` |
| B3 | **Clasificador en el navegador del celular** (TFLite int8 en WebAssembly, sin internet tras cargar) | `web/clasificador/` |
| B4 | **Bot sugiere la clase** con la CNN y la guarda (`clase_sugerida`, `confianza_sugerida`, `modelo_sugerencia`) | `bot/`, `dataset/clasificar.py`, `db/` |
| C1 | Firmware: gráfica en vivo, umbrales en NVS, descarga de CSV por WiFi, watchdog, reintentos GPS/SD, LED de estado; arreglado `exp_NNN.csv` (límite de 5 archivos de la librería SD) | `firmware/nodo-sensores/` |
| C2 | Montaje final del DevKit V1 con todos los sensores, diagrama y Wokwi actualizado | `docs/montaje.md`, `firmware/nodo-sensores/wokwi/` |
| D1 | Tablero: pestaña **Reportes y eventos** ordenada con el heap (severidad × tránsito × reincidencia) | `dashboard-java/` |
| D2 | **Demo en un comando** con base DEMO separada; guion de 5 min | `demo/`, `docs/demo.md` |
| D3 | **34 pruebas pytest** + GitHub Actions (pytest y PlatformIO, solo si cambian sus carpetas, con caché) | `tests/`, `.github/workflows/` |
| E1 | Texto en inglés para Overleaf (sección por sección) y `informe_overleaf.zip` | `docs/cambios_informe.md`, `05_SOFTWARE\para_anzola\` |

Hecho antes (3-nov y anteriores): firmware base (ADXL345 FIFO+DMA, detector, maniobras, E1–E4), ETL + SQLite, modelo de
riesgo con plan B, bot, mapa, tablero, dataset de fotos (ingesta, etiquetador, escala ArUco), tarjeta ArUco, informe IEEE.

## Probado y NO probado

| Pieza | Probado | NO probado |
|---|---|---|
| Firmware (3 entornos + 10 pruebas) | **Compila** (7-nov, con el DMA de 8 bytes: RAM 66 348 B, 20,2 %; flash 944 357 B, 48,0 %); JS de la página revisado con Node | **Nada en placa** (remontaje de SD, reinicio de UART2, watchdog, LED, descarga por WiFi, overruns de E1) |
| Wokwi | `diagram.json` con DevKit V1 + DHT22 | La simulación |
| **Captura en vivo** | Con los 3 recorridos reales reproducidos (×20): capturas **idénticas** al export (31 415 / 43 222 / 81 560 muestras) y aceptadas por el validador; corte de conexión sin pérdida; detector en flujo = por lotes; botones y vista en vivo en el navegador | **Con el iPhone en el carro** (punto de acceso + acceso remoto) |
| Recorridos reales del 7-nov | Validador: 100 Hz, 0 cortes, GPS ~99 %. Corregir: 1 min quieto (inicio del 01, final del 01 y 03), 36 km/h en el 01 | Sin etiquetas: no hay detector calibrado ni métricas. Detector en vivo SIN calibrar: 4 / 11 / 81 disparos (no son resultados) |
| Conversor de vueltas | 15 pruebas (formatos, sinónimos, paradas, errores) | Con un cronómetro real del iPhone |
| Validador de campo | Con exports y fotos fabricados, con los sintéticos y con los **3 exports reales de phyphox iOS** | Fotos HEIC reales y la planilla real |
| Planilla | Con una planilla de ejemplo sobre las fotos sintéticas | Con el CSV real de Google Sheets |
| Ingesta, etiquetador, escala | Con 432 fotos SINTÉTICAS (3-nov) | Con fotos reales del iPhone |
| Modelo de fotos | **SINTÉTICO**: V3 int8 cae (0,90 → 0,57–0,70) y corre en núcleos de referencia; V2 int8 PTQ 0,93; QAT de 3 épocas 0,88 | Con fotos reales; QAT con más épocas; pre-entrenamiento con Kaggle (no descargado) |
| Clasificador en el navegador | Chromium del PC: int8 V2 SINTÉTICO, 19 ms, misma clase que Python | **En el iPhone** (Safari) |
| Bot con CNN | `dataset.clasificar` en el venv del bot (LiteRT); guardado de la sugerencia (pytest) | **Con Telegram real** |
| Tablero Java | Compila con Ant; `PruebaPrioridad` y `PruebaEstructuras` pasan; capturas sin pantalla con datos DEMO | En el IDE NetBeans con el ratón |
| Demo en un comando | Base DEMO (40 eventos, 10 reportes, riesgo DEMO-SINTETICO) generada; sintaxis del `.ps1` | `iniciar.ps1` de punta a punta (abre ventanas) |
| Detector, recorridos, riesgo | Con sintéticos | Con datos reales |
| GitHub Actions | Python: falló la 1.ª vez (faltaba `reportlab`), corregido; firmware en curso | Ver la pestaña *Actions* |

## Cifras reales ya calculadas (implementación, no resultados de campo)

| Cifra | Valor | Fuente |
|---|---|---|
| Grafo de Tunja | 4 054 nodos, 5 775 tramos, 537,6 km | `etl.osm_tunja` |
| Firmware esp32dev (5-nov) | RAM 66 348 B (20,2 %), flash 944 269 B (48,0 %) | `pio run` |
| Red 1D del nodo | 788 parámetros; 3 152 B float32 vs. 872 B int8 | `entrenar_detector.py` |
| Modelos de fotos (tamaño del archivo, no depende de los datos) | MobileNetV3-Small: 3 653 KB float32 / 1 182 KB int8; MobileNetV2: 8 691 KB / 2 647 KB | `dataset.modelo` |
| Tarjeta ArUco | 4 marcadores detectados, 79,9 mm de 80 (PDF a 300 dpi) | `dataset.tarjeta_aruco` |
| Tablero | 108 comparaciones (geohash) vs. 5 775 por búsqueda | `PruebaEstructuras` |

## GitHub: auditoría del 5-nov (no se cambió nada)

| Cuenta | Persona | Organización | Repo `via-viva` |
|---|---|---|---|
| `andresscardens` | Andrés | **owner** | admin |
| `Juandi-1` | Juan Diego | **owner** | admin |
| `juanfelipegarciacarvajal444-rgb` | Juan Felipe (Pipe) | **owner** | admin |
| `dany286-ri` | Dany | member | **read** |

Organización: permiso base *read*, los miembros pueden crear repos (también públicos), **2FA no obligatorio**, plan
gratuito (no permite proteger `main` en un repo privado). **Recomendado** (lo aplica Andrés, issue #17):
1. **Un solo owner** (Andrés); Juan Diego, Pipe y Dany como **Member** con rol **Write** en `via-viva`
   (*Settings → Collaborators and teams*; o un equipo "via-viva" con Write).
2. Exigir **2FA** a la organización y quitar a los miembros el permiso de crear repositorios públicos.
3. Sin protección de ramas (plan gratuito): mantener la regla de `CONTRIBUTING.md` (PR y revisión de Andrés).

## Discrepancias corregidas el 5-nov

- `CLAUDE.md`, README, diagrama y experimentos decían "BME280 o DHT22": ahora **DHT22** elegido (BME280 solo opcional).
- `docs/protocolo_fotos.md` y `dataset/README.md` usaban la carpeta `VIA_VIVA_fotos` (no existe): ahora
  `VIA_VIVA/02_DATOS/fotos/AAAA-MM-DD_nombre/` y `.../phyphox/`.
- `analysis/README.md`: phyphox "a la tasa máxima" → **iPhone ~100 Hz**, 1 min quieto al inicio **y al final**, cronómetro por vueltas.
- Notebook mencionaba la ESP32-S3; `db/schema.sql` describía la foto del evento como de la ESP32-CAM.
- `docs/README.md` no listaba los documentos nuevos. Issue #20 hablaba de `VIA_VIVA_fotos`.
- Requirements: pandas 3.1, TensorFlow 2.21 y scikit-learn 1.9.1 los bloqueaba **Smart App Control** (ya desactivado);
  quedan fijados pandas 3.0.0, TensorFlow 2.20.0 y scikit-learn 1.7.2, que están probados.

## Carpeta `05_SOFTWARE\para_anzola` (fuera del repo): qué está desactualizado

| Archivo | Problema | Qué hacer |
|---|---|---|
| `VIA_VIVA_Intro_RelatedWork_Methodology.docx` | Habla de la **ESP32-CAM** y la S3 (3 menciones de cámara); no menciona el dataset de fotos, DHT22/BH1750, celular, láser/OBD2 a futuro | Usar `docs/cambios_informe.md` |
| `VIA_VIVA_informe_final_borrador.pdf` | Del 3-nov a las 7:39 (4 páginas), **antes** del cambio de plan | Reemplazarlo por lo de Overleaf |
| `demo.md` | Guion viejo (foto de la ESP32-CAM) | Usar `docs/demo.md` del repo |
| `poster.md` | Igual al del repo (sin el dataset de fotos ni el clasificador en el celular) | Actualizar el póster con la sección de imágenes |
| `informe_overleaf.zip` | **Nuevo (5-nov)**: `report/` actual para subir a Overleaf | — |

## Qué falta, por persona (fechas vigentes)

### Andrés (`andresscardens`)
1. **Ya:** aplicar los roles recomendados (#17). Crear `C:\Users\AC\.kaggle\kaggle.json` para bajar el dataset de Kaggle
   (`dataset.externos --descargar-kaggle`). *(5-nov)*
2. Bajar de Drive cada día fotos, planilla y phyphox; correr `herramientas.validar_campo` y `dataset.ingesta`; publicar el
   resumen en #22. *(6–10 nov)*
3. Con fotos etiquetadas: `dataset.escala --validar` y `dataset.modelo --comparar` (más épocas de QAT) (#24). *(11-nov)*
4. Recorridos → `etl.recorridos` → riesgo `--fuente auto` (#9); **9-nov decide plan B** (#12); validación en campo (#10).
5. Bot con celulares (#8) y `demo\iniciar.ps1` de punta a punta. *(10-nov)*

### Juan Diego (`Juandi-1`)
1. **Fotos con el iPhone 15** según el protocolo, planilla al día (#21). *(6–9 nov)*
2. Tarjetas ArUco impresas y verificadas (#19). *(6-nov)*
3. Probar el **clasificador en el iPhone** (`python web\clasificador\preparar.py --servir` en el PC de Andrés). *(8-nov)*
4. Pasar `docs/cambios_informe.md` a **Overleaf** (`informe_overleaf.zip`) (#13); póster, video y pitch (#14). *(12-nov)*
5. Etiquetar con Pipe (#23). *(10-nov)*

### Juan Felipe — Pipe (`juanfelipegarciacarvajal444-rgb`)
1. 3 recorridos hechos el 7-nov ✅. Próximos: con la **captura en vivo** (`analysis/README.md`, plan A) para que salgan **etiquetados**; 1 min quieto al inicio y al final; ≤ 30 km/h (#5). *(8-nov)*
2. Espectro, fs y calibración del detector (#6); entrenar el detector del nodo (#7). *(9-nov)*
3. Coordinar las salidas de fotos (#21) y etiquetar (#23). *(9–10 nov)*

### Dany (`dany286-ri`)
1. Cuando llegue el hardware: montaje con `docs/montaje.md` y las 10 pruebas (#1, #18); firmware completo con la página
   nueva, descarga por WiFi y LED (#2). *(7–8 nov)*
2. E1–E4 y corriente (#4). *(9-nov)*

## Bloqueos

| Bloqueo | Quién lo destraba |
|---|---|
| Falta `kaggle.json` para descargar el dataset externo | Andrés |
| Hardware por llegar (ESP32 DevKit V1, DHT22, BH1750, cable, termohigrómetro) | Compras |
| Sin datos reales todavía | Salidas de campo (todos) |
| Convenio USTA–Alcaldía para el piloto (apoyo de palabra) y respuestas a los radicados | Andrés / USTA |

## Estado local del PC de Andrés (no está en Git)

- `data/via_viva.db` (real, sin eventos ni reportes) y **`data/via_viva_demo.db`** (copia con datos DEMO para la demo).
- `data/raw/fotos_sintetico`, `data/procesado_sintetico`, `data/raw/phyphox_sintetico`, `data/externo/SINTETICO_voc`:
  datos **SINTÉTICOS** de prueba. `dataset/salidas/20261105-0752-SINTETICO/`: modelo de prueba.
- Venvs: `etl`, `analysis`, `bot` (con LiteRT), `dataset` (con pytest) y `%USERPROFILE%\.venvs\vv-modelo` (TensorFlow
  2.20, tf_keras, tfmot). Smart App Control **desactivado** el 5-nov por Andrés.
- `web/clasificador/vendor` y `modelo/`: librerías y modelo copiados por `preparar.py` (se regeneran).

## Fuentes externas y licencias

| Fuente | Qué se usa | Licencia / condiciones |
|---|---|---|
| OpenStreetMap (osmnx / Overpass) | Grafo de calles; teselas del mapa web | ODbL 1.0 — "© OpenStreetMap contributors"; políticas de uso de teselas y Overpass |
| IDEAM — datos.gov.co `s54a-sgyg` | Precipitación (datos crudos) | CC BY-SA 4.0 |
| Alcaldía de Tunja — datos.gov.co `4ryc-k7fx` | Barrios y veredas (punto y sector) | CC BY-SA 4.0. Dato abierto: distinto de los datos pedidos por oficio |
| OpenTopoData (SRTM 30 m) | Elevación de los nodos | SRTM: dominio público (NASA/USGS); API con límites de uso |
| Gobernación de Boyacá (RSS) | Títulos y enlaces de noticias | Contenido © Gobernación; solo título, resumen y enlace |
| Datos pedidos a Alcaldía / Tránsito (si llegan) | Inventario de huecos, siniestros | **No se publican** sin permiso (`data/alcaldia/`, ignorada) |
| Open-Meteo | Temperatura y humedad por hora para las fotos | CC BY 4.0 ("Weather data by Open-Meteo.com") |
| Kaggle `andrewmvd/pothole-detection` (MakeML) | Pre-entrenamiento hueco / no-hueco (si se descarga) | Database Contents License v1.0; citar MakeML |
| Hugging Face `Duranishhh/baches-carreteras` | **No se usa** | Licencia de imágenes no documentada |
| Leaflet 1.9.4 · sqlite-jdbc 3.47.1.0 · python-telegram-bot 22 | Mapa, tablero, bot | BSD-2 · Apache 2.0 · LGPL-3.0 |
| PyTorch · scikit-learn · emlearn | Detector del nodo | BSD-3 · BSD-3 · MIT |
| TensorFlow · tf_keras · tensorflow-model-optimization · LiteRT · TensorFlow.js / tfjs-tflite | Modelo de fotos, QAT, bot y navegador | Apache 2.0 |
| OpenCV · Pillow · pillow-heif · ReportLab | Dataset, ArUco, HEIC, PDF | Apache 2.0 · MIT-CMU · BSD-3 (libheif LGPL) · BSD |
| TinyGPSPlus · VL53L0X (Pololu) | Firmware | LGPL-2.1 · licencia de Pololu |
