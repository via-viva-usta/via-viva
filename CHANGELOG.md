# Cambios

## 2026-11-12 — tablero en línea: íconos SVG y cifras con tendencia (rama `web/iconos-tendencia`)

- Un solo juego de íconos SVG en `web/en_linea/tablero.html` (trazo 1,75, puntas rectas, sin archivos ni fuentes aparte):
  reemplaza los caracteres ?, ◐, ✕, ✓ y × de la barra, los filtros activos y la lista, y suma pictogramas de hueco y
  golpe en el detalle.
- Las cifras Huecos abiertos, Severidad alta y Reparados muestran una mini línea de 8 ventanas de 7 días y una frase
  («3 menos que 7 días antes»). Respeta severidad y tipo, no el periodo. Funciones en `reglas.js`
  (`abiertoEn`, `serieSemanas`, `textoTendencia`) con pruebas: `node --test tests/web/*.test.mjs` (5 pasan).
- Revisado con los datos de prueba en el navegador (1440 px oscuro y claro, 390 px sin desborde). Sin probar contra
  Supabase real.

## 2026-11-11 — roles definitivos de la salida de campo

- iPhone A = Anzola (phyphox + punto de acceso); PC de captura = su Lenovo, marca con el teclado; iPhone B = Pipe, solo
  video; `/marcar` solo para un tercero; el conductor solo conduce. Tabla «Rol por persona» en `README_SALIDA.md`;
  `CLAUDE.md`, `ARQUITECTURA.md`, `viaviva/README.md` y `analysis/README.md` (histórico) al día.
- `config/phyphox/VIA_VIVA_2.0.phyphox`: el experimento del 7-nov **sin datos ni horas**, para instalar en el iPhone A
  (o crearlo como «Experimento simple»). Sin probar todavía en ese iPhone.

## 2026-11-11 — captura en el PC de otra persona

- Instalación limpia probada en Windows (clon nuevo, sin `.env` ni datos): `instalar_pc.ps1` → `doctor` →
  `SALIDA_DE_CAMPO.cmd` → `capture --replay … --por-http` y `capture --source phyphox` (sin iPhone: arranca y reintenta).
- `--replay ejemplo` / `doctor --simulado ejemplo`: recorrido SINTÉTICO para practicar sin datos de campo.
- `instalar_pc.ps1` acepta Python 3.11–3.13 y avisa si falta ffmpeg; `SALIDA_DE_CAMPO.cmd` llama a `viaviva.cmd` por su ruta.
- `VIAVIVA_PIN`, `VIAVIVA_IP_PC`, `VIAVIVA_IPS_EDITOR` (opcionales, sin claves). Una sesión copiada en zip rehace sus
  etiquetas desde `sesion.sqlite`.
- **Mac** (`viaviva.sh`, `viaviva/instalar_mac.sh`) y **Docker** (`Dockerfile`, `docker-compose.yml`, `.dockerignore`,
  solo captura del PC): **sin probar** (no hay Mac ni Docker en el PC de AC). Pasos en `README_SALIDA.md`.

## 2026-11-11 — video HEVC y documentación al día

- **Importar video:** se guarda el códec; si es HEVC o el navegador no puede reproducirlo, la revisión lo dice y ofrece
  «Convertir a H.264» con ffmpeg (opcional, en segundo plano; conserva el original y el desfase). Sin ffmpeg explica qué hacer.
- Documentación: rutas `pi/` → `viaviva/`, ESP32 como historia, phyphox en el puerto 80, resumen vigente en `docs/ESTADO.md`.
- **Decisión de diseño:** el sitio en línea conserva la marca de Dany; el tema B queda para el tablero local y los
  reportes (`docs/DISENO.md`). El tema B de la página anterior sigue archivado, sin restaurar.
- Suite: 86 pasaron, 1 omitida (TensorFlow); Ruff limpio.

## 2026-11-11 — integración con `main` (portada y tablero en línea de Dany)

- `main` ya traía la portada y el tablero en línea reorganizados (PR #30: `index.html` = portada,
  `tablero.html` = tablero, marca propia). Al fusionar, **en `web/en_linea/` quedó la versión de `main`**.
- El tema B · Cartografía que se había aplicado a la página anterior (una sola página) no se perdió: está en
  `docs/archivo/en_linea_tema_b_codex_2026-11-11/` y en el commit d8f9264. Llevarlo a la estructura nueva es una
  decisión de diseño pendiente del equipo.

## 2026-11-10 — un solo sistema: campo → sesiones → video → revisión → dataset → demo

- **Diseño:** dos temas con los mismos componentes (`docs/diseno/`): A · Asfalto (oscuro) en Campo, Sesiones,
  Revisión, Dataset y Demo; B · Cartografía (claro) en el Tablero, la entrada y los reportes. Navegación común.
- **Sesiones** (`/sesiones`): cada salida con resumen, calidad, recorrido, video y avance de la revisión.
- **Importar video** (dentro de la revisión): se arrastra el .mov/.mp4 del iPhone B y la app lo sincroniza sola con
  los destellos de `/sync`; si no los ve, usa la fecha del archivo (± 1–2 s) y deja ajustar el desfase.
- **Revisión** (`/revision?s=…`): línea de tiempo con señal, eventos, marcas y video; confirmar (1–7 / Enter),
  corregir o descartar (X). Se guarda en `sesion.sqlite` y rehace las etiquetas que usan detector y dataset.
- **Carga de video:** límite de 8 GiB aplicado mientras se recibe; cada intento se guarda con nombre único y no pisa
  el video anterior. `.m4v` se sirve con su tipo MIME reproducible.
- **Dataset** (`/dataset`): un botón construye las ventanas y muestra balance, cobertura, umbrales por clase,
  calibración por salida y clasificador.
- **Demo** (`/demo`): 4 pasos de 30 s (captura → detección → mapa → reporte) con datos en vivo o `--replay`.
- **Tablero en línea:** aplicado el tema B · Cartografía, con paleta cálida, titulares Instrument Serif, tarjetas, filtros
  adaptables y el tema claro como predeterminado; se conserva la opción oscura.
- R7 del PC rotulado «provisional, PC»; suite: 85 pasaron, 1 omitida; Ruff limpio.

## 2026-11-10 — conexión con phyphox

- phyphox en iOS responde en el **puerto 80** (no 8080): la URL por defecto es `http://172.20.10.1` y `doctor` y
  `capture` **autodetectan 80/8080**; si la captura pierde la conexión, vuelve a probar los dos puertos.
- Los nombres de los buffers (aceleración, ubicación, giroscopio) se leen de `/config` (`inputs`); si el experimento no
  los declara, se usan los de «VÍA VIVA 2.0». `doctor` muestra el mapeo y verifica muestras y GPS.
- `viaviva doctor [--url …]` deja la URL que respondió en `.env` (`VIAVIVA_PHYPHOX_URL`; `--no-guardar` para evitarlo).
- Minuto quieto: tolerancia de **5 km/h** (antes 2): el GPS del iPhone marca 3–5 km/h con el carro detenido.
## 2026-11-10 — tablero en línea reorganizado (rama `web/interfaz-dany`)

- **Portada** (`web/en_linea/index.html`) y tablero en `tablero.html` (los enlaces viejos con `?demo`/`?kiosco` se
  redirigen). Marca de estilo brutalista (asfalto, blanco, amarillo de señal), Archivo Black + Inter alojadas en el sitio
  (OFL, `fuentes/`), tablero oscuro por defecto. Menos saturación: filtros y leyenda plegados, filas de una línea, 15 por
  página, datos que entran por partes. Imágenes de la portada desde el modo DEMO, con sello.
- **Tablero en línea:** mapa en dos modos (Huecos / Riesgo por tramo) para que los colores no se mezclen; cifras que
  también son atajos; filtros Abiertos/Reparados/Todos + severidad, tipo y periodo; pestañas «Para atender» (prioridad
  explicada), «Tramos en riesgo» y «Tendencia» (nuevos vs. reparados por semana, con tabla); detalle en el panel;
  indicador del último dato; ayuda «Cómo leer este tablero»; celular, pantalla fija e impresión revisados.
  Código separado en `reglas.js`, `carga.js`, `mapa.js`, `app.js` y `tema.js`.
- **Correcciones de datos:** lectura paginada de Supabase (se cortaba en 1 000 filas); prioridad del tablero local con
  la severidad medida (antes todos los huecos valían 3; prueba nueva); número de hueco repetido entre equipos en la
  importación; CSV descargado reutilizable para importar; fechas y semanas en hora de Tunja.
- `tramos_demo.py` pasa a `herramientas/` y marca su archivo como DEMO. Hallazgos y propuestas: `docs/REVISION_INTERFAZ.md`.

## 2026-11-10 — cierre del software (rama `ac/cierre-software`)

- **Fase A — captura de campo con el PC + phyphox:** `viaviva doctor` (LISTO / FALTA), `viaviva capture` con reconexión
  sin pérdida, UTC del PC por muestra, sesión `sesion_AAAA-MM-DD_hhmm` con bitácora, SQLite y `RESUMEN.md`; marcas 1–7 +
  U con retardo −1 s (teclado, `/captura` y `/marcar` en el celular con PIN); `/sync` con reloj y destello para el video;
  `--replay` directo o por HTTP contra un simulador de phyphox; `SALIDA_DE_CAMPO.cmd` y `README_SALIDA.md`.
- **Fase B:** detector calibrable (`config/detector.yaml`: pico, RMS, jerk, normalización por velocidad, severidad y
  confianza; eje vertical por gravedad), evaluación P/R/F1 y calibración dejando una salida afuera; dataset de ventanas
  de 2 s con `manifest.csv`, `calidad.md` y fotos asociadas; esqueleto TFLite (SINTÉTICO, etapa siguiente).
- **Fase C:** modo Raspberry Pi según el manual v3 (ADXL #2 en CE1, `gpio-shutdown`, sensores opcionales, hotspot del
  celular, escritura cada 5 s). Sin probar en hardware.
- **Fase D:** tablero en línea (MapLibre + Chart.js + Pico, Netlify) con Supabase, roles por fila, cambios de estado y
  reparaciones desde la web aplicados por la Pi; sincronización de huecos además de eventos y riesgo.
- **Fase E:** R7 sin ESP32 (medido en el PC), ruff + cobertura en la CI, scraping revisado, documentación
  (`docs/ARQUITECTURA.md`, `DATOS.md`, `SEGURIDAD.md`, `DISENO.md`, `NUBE.md`, `SCRAPING.md`, `R7.md`).
- Cambios de base: `pi/` → `viaviva/`; servidor de la biblioteca estándar → FastAPI (decisión del 9-nov; el anterior en
  `docs/archivo/`); tabla de R7 con ESP32 archivada.
- Corrección: el mensaje del commit 4ef9c50 dice "74 pruebas"; eran **72**.

## 2026-11-07

- Raspberry Pi 4 como nodo central (`pi/`), aplicativo con roles, huecos con estado, exportables y cola a Supabase;
  bot de Telegram pospuesto (`futuro/bot/`). Scraping diario, R7 con Welford, R3 por clase, captura en vivo de phyphox.
