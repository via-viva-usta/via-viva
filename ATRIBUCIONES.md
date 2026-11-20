# Atribuciones y licencias de terceros

Este archivo lista el software, los datos y los recursos de terceros que VÍA VIVA **sirve, incluye o descarga**, con su
licencia según cada proyecto. Se revisó el 20-nov-2026 contra el código de `main`; si se agrega una librería o una
fuente, se añade aquí en el mismo PR.

**Licencia de VÍA VIVA:** el repositorio todavía **no tiene licencia** (no hay `LICENSE`). Elegirla es una decisión del
equipo y, si aplica, de la Universidad (titularidad de lo hecho en el curso). Mientras tanto, el código no se puede
reutilizar fuera del proyecto sin permiso de sus autores.

## Software que se sirve al navegador

| Recurso | Versión | Licencia | Dónde se usa | Cómo llega |
|---|---|---|---|---|
| [MapLibre GL JS](https://github.com/maplibre/maplibre-gl-js) | 6.17.0 | BSD-3-Clause | Mapa del tablero en línea y de la app local | jsDelivr (web); copia local que bajan los instaladores (`viaviva/web/vendor/`, ignorada) |
| [Chart.js](https://github.com/chartjs/Chart.js) | 4.6.1 | MIT | Gráfico de tendencia (`web/en_linea/app.js`) | jsDelivr |
| [supabase-js](https://github.com/supabase/supabase-js) | 2.119.0 | MIT | Sesión y lectura del tablero en línea | jsDelivr |
| [Pico CSS](https://github.com/picocss/pico) | 2.1.1 | MIT | Base de estilos del tablero en línea | jsDelivr |
| [model-viewer](https://github.com/google/model-viewer) | 4.4.0 | Apache-2.0 | Modelos 3D del menú (`web/en_linea/menu.js`) | jsDelivr |
| [SheetJS Community Edition](https://git.sheetjs.com/sheetjs/sheetjs) | 0.20.3 | Apache-2.0 | Descarga en Excel del tablero en línea | cdn.sheetjs.com |
| Archivo Black, Inter (vía [Fontsource](https://fontsource.org/)) | 5.3.0 | SIL OFL 1.1 | Tipografía de la web y la app | Copias en `web/en_linea/fuentes/` con su texto OFL |
| Modelos 3D de [Kenney](https://kenney.nl/) | — | CC0 1.0 | Menú del sitio | Copias en `web/en_linea/modelos/` (origen en su `LEEME.md`) |

## Datos y mapas

| Fuente | Licencia | Dónde | Atribución que exige |
|---|---|---|---|
| [OpenStreetMap](https://www.openstreetmap.org/copyright) (calles de Tunja, vía osmnx/Overpass) | ODbL 1.0 | `web/en_linea/datos/tramos.geojson`, `viaviva/web/datos/calles_tunja.json`, base local | «© OpenStreetMap contributors»; lo derivado se comparte con la misma licencia (ver `LEEME.md` en esas carpetas) |
| [OpenFreeMap](https://openfreemap.org/) (teselas del mapa base) | Datos OSM (ODbL); servicio gratuito sin SLA | Fondo del mapa, web y app | «© OpenStreetMap · OpenFreeMap» (la pone el mapa) |
| Barrios y veredas de Tunja, [datos.gov.co, conjunto 4ryc-k7fx](https://www.datos.gov.co/d/4ryc-k7fx) | **Por confirmar** en la ficha del conjunto (la portada dice CC BY-SA 4.0; `README.md` y `docs/DATOS.md` dicen solo «datos abiertos») | ETL (`etl/barrios_tunja.py`), cifras de la portada | Según la licencia confirmada |
| IDEAM, precipitación vía datos.gov.co (Socrata) | CC BY-SA 4.0 según `docs/SCRAPING.md` | Scraping diario (`etl/scraping/clima_ideam.py`), modelo de riesgo | Citar IDEAM y la licencia donde se muestren |
| Elevación SRTM vía OpenTopoData | Sin licencia indicada en el repo: **por confirmar** | `etl/elevacion.py` | — |

## Datasets externos (solo evaluación; nada de esto está en Git)

Se usan **solo para comparar** detectores; no son métricas de Tunja ni sirven para fijar umbrales
(`docs/INVESTIGACION_DETECTORES.md`).

| Dataset | Licencia según su fuente | Restricción importante |
|---|---|---|
| PVS (Passive Vehicular Sensors) | CC BY-NC-ND 4.0 | No comercial y **sin derivados**: no se publican ventanas, características ni modelos hechos con PVS |
| RoadSens-4M (figshare, doi 10.6084/m9.figshare.30341143.v3) | Datos CC BY 4.0 | Citar el doi |
| Kaggle (pre-entrenamiento de fotos, `dataset/externos.py`) | Según cada conjunto (p. ej. DbCL v1.0) | Revisar la licencia de cada conjunto antes de usarlo |

## Python (se instalan con pip; no se redistribuyen en el repo)

Licencias según PyPI: FastAPI (MIT), Uvicorn (BSD-3), PyYAML (MIT), segno (BSD-3), python-dotenv (BSD-3), openpyxl
(MIT), ReportLab (BSD), NumPy / pandas / SciPy / scikit-learn (BSD-3), requests (Apache-2.0), cryptography
(Apache-2.0 o BSD), OpenCV (Apache-2.0), Pillow (MIT-CMU), osmnx (MIT), Adafruit Blinka y CircuitPython (MIT),
gpiod / libgpiod (LGPL-2.1+), gpiozero (BSD-3), smbus2 (MIT), spidev (MIT), TensorFlow (Apache-2.0).
