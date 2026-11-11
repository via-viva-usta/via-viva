# Cambios

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
