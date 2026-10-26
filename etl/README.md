# etl/

Pipeline en Python: grafo de calles de Tunja (OpenStreetMap con osmnx), web scraping de fuentes públicas,
limpieza y carga a SQLite (`db/schema.sql`).

## Instalación (una vez, Windows, desde `via-viva/`)

```powershell
py -3.11 -m venv etl\.venv
etl\.venv\Scripts\python -m pip install -r etl\requirements.txt
copy .env.example .env    # opcional: cambiar VIA_VIVA_DB, SCRAPER_USER_AGENT, SOCRATA_APP_TOKEN
```

Todos los comandos se corren **desde `via-viva/`** como módulos (`-m etl....`).

## Scripts

| Comando | Qué hace | Salida |
|---|---|---|
| `etl\.venv\Scripts\python -m etl.db` | Crea la base y aplica el esquema | `data/via_viva.db` |
| `etl\.venv\Scripts\python -m etl.osm_tunja` | Descarga el grafo vial de Tunja y carga `tramos` y `nodos` | `data/osm/tunja_drive.gpkg`, `.graphml` |
| `etl\.venv\Scripts\python -m etl.scraping.clima_ideam` | Lluvia diaria de estaciones IDEAM a ≤15 km (últimos 30 días) | filas `tipo='clima'` en `fuentes_externas` |
| `etl\.venv\Scripts\python -m etl.scraping.noticias --revisar` | Revisa robots.txt y respuesta de cada fuente de noticias | solo consola |
| `etl\.venv\Scripts\python -m etl.scraping.noticias` | Descarga las fuentes habilitadas y guarda las relevantes | filas `cierre_vial` / `accidente` / `obra` |
| `etl\.venv\Scripts\python -m etl.barrios_tunja` | 154 barrios y veredas de Tunja (Alcaldía, datos abiertos `4ryc-k7fx`) | tabla `barrios` |
| `etl\.venv\Scripts\python -m etl.elevacion` | Elevación de los nodos (SRTM 30 m, OpenTopoData) y pendiente de cada tramo | `nodos.elevacion_m`, `tramos.pendiente_pct` |
| `etl\.venv\Scripts\python -m etl.geohash` | Prueba del geohash escrito a mano | solo consola |

`data/` (base, GeoPackage, caché) está en `.gitignore`: cada quien la regenera con estos comandos.

## Resultados de la primera corrida (26-oct-2026)

Calculados por los scripts, no estimados:

**Grafo de Tunja** (`network_type="drive"`, polígono del municipio según Nominatim, incluye vías rurales):

| Medida | Valor |
|---|---|
| Nodos (intersecciones y extremos) | 4 054 |
| Aristas dirigidas (como las entrega osmnx) | 10 604 |
| Tramos no dirigidos (filas en `tramos`) | 5 775 |
| Longitud total de tramos | 537,6 km |
| Tramos con etiqueta `surface` | 11,0 % |
| Tipos más comunes | residential 4 747 · primary 333 · secondary 261 · tertiary 156 · unclassified 148 · trunk 77 |

Solo el 11 % de los tramos tiene superficie en OSM: para el modelo de riesgo habrá que completarla en campo o con el
inventario de la Alcaldía.

**Clima IDEAM** (conjunto `s54a-sgyg`, 26-sep a 25-oct-2026): 5 estaciones a ≤15 km con datos recientes
(Tunja-UPTC 2,5 km, Motavita 11,2 km, Ramiriquí 12,7 km, Siachoque 13,9 km, Samacá 14,5 km), 29 días cada una,
145 filas. Volver a correrlo no duplica: actualiza los días ya cargados.

**Noticias:** la plantilla funciona (lee RSS y HTML, revisa robots.txt, clasifica por palabras clave), pero en la
prueba ninguna entrada de los feeds hablaba de cierres o accidentes, así que no se guardó ninguna noticia.

## Notas y limitaciones

- **Overpass (OSM) se satura a veces** (error 502/504): `osm_tunja.py` reintenta con espera y prueba servidores espejo.
  Después de la primera descarga usa la caché de `data/osm/cache/`.
- **IDEAM son datos crudos** (sin validación). El nombre del departamento y de la estación cambió de formato en el
  conjunto (`BOYACÁ` → `Boyacá`, sufijo ` - AUT [código]`), por eso se filtra por código de estación y distancia.
  Cada día guarda su `cobertura_dia` en `extra_json` (1,0 = día completo).
- **Scraping responsable:** `etl/scraping/comun.py` revisa robots.txt, respeta `Crawl-delay` (mínimo 2 s) y se
  identifica con `SCRAPER_USER_AGENT`. Que robots.txt lo permita **no** reemplaza leer los términos de uso del sitio.
- Fuentes de noticias revisadas el 26-oct: Gobernación de Boyacá (RSS oficial, habilitada); Boyacá 7 Días
  (robots.txt lo permite, deshabilitada hasta revisar términos); Alcaldía de Tunja (sin robots.txt, página en
  JavaScript: 0 entradas con requests).

## Pendiente

- Ajuste de eventos y reportes al tramo más cercano en la carga (hoy lo hace `risk_model.variables` al vuelo),
  deduplicación por geohash, tabla `peligros`.
- Carga de eventos del nodo y del bot.

Pendiente por tramo y barrio ya están (Fase 4): ver `risk_model/README.md`.
