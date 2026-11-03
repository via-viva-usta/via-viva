# db/

| Archivo | Qué es |
|---|---|
| `schema.sql` | Esquema SQLite: `tramos`, `eventos`, `reportes`, `fuentes_externas`, `riesgo` + `nodos`, `barrios`, `variables_tramo` (diagrama en `docs/diagramas/03_entidad_relacion.md`) |
| `acceso.py` | **Capa de acceso a datos.** Todo el código abre la base solo por aquí (`conectar()`, `leer_df()`, `resumen()`). La conexión sale de `.env` (`VIA_VIVA_DB_URL`) |
| `reconstruir.ps1` | Reconstruye la base desde cero (entorno virtual + ETL en orden) |

El archivo `.db` se genera localmente y **no** se sube al repositorio (`data/` está en `.gitignore`).

## Reconstruir la base desde cero (PowerShell, Windows)

Requisitos: Python 3.11 (`py -3.11 --version`) e internet. Desde la carpeta `via-viva\`:

```powershell
powershell -ExecutionPolicy Bypass -File db\reconstruir.ps1 -Limpiar
```

El script hace, en orden (se puede correr paso a paso con los mismos comandos):

```powershell
copy .env.example .env                                    # si no existe
py -3.11 -m venv etl\.venv
etl\.venv\Scripts\python -m pip install -r risk_model\requirements.txt   # incluye etl\requirements.txt
etl\.venv\Scripts\python -m db.acceso                     # 1. crea la base y aplica schema.sql
etl\.venv\Scripts\python -m etl.osm_tunja                 # 2. grafo de calles (OSM): tramos y nodos
etl\.venv\Scripts\python -m etl.barrios_tunja             # 3. barrios y veredas (Alcaldía, datos abiertos)
etl\.venv\Scripts\python -m etl.elevacion                 # 4. elevación (SRTM 30 m) y pendiente por tramo
etl\.venv\Scripts\python -m etl.scraping.clima_ideam      # 5. lluvia diaria IDEAM (últimos 30 días)
etl\.venv\Scripts\python -m etl.scraping.noticias         # 6. noticias de cierres y accidentes
etl\.venv\Scripts\python -m risk_model.variables          # 7. tabla de variables por tramo
etl\.venv\Scripts\python -m db.acceso                     # resumen: filas por tabla
```

Después, según haya datos: `python -m etl.recorridos` (recorridos de phyphox), el bot (`bot/`) y
`python -m risk_model.modelo --guardar` (ver `risk_model/README.md`).

### Prueba desde cero (2-nov-2026)

Se copió el repositorio a una carpeta temporal **sin** entornos virtuales, sin `data/` y sin `.env`, y se corrió
`db\reconstruir.ps1 -Limpiar`. El resultado está al final de este archivo.

Ojo con la reproducibilidad: OpenStreetMap, IDEAM y OpenTopoData son fuentes **vivas**. El conteo de tramos puede cambiar
un poco entre días (en la prueba del 2-nov salieron 4 745 tramos residenciales contra 4 747 el 26-oct) y la lluvia depende
de la fecha. El grafo descargado queda guardado en `data/osm/` para repetir un análisis con los mismos tramos.

## Capa de acceso (`db/acceso.py`) y migración a PostgreSQL/PostGIS

```python
from db.acceso import conectar, leer_df
con = conectar()                                   # SQLite: crea la base si no existe y aplica el esquema
df = leer_df("SELECT tipo_via, COUNT(*) n FROM tramos GROUP BY 1")
```

Para migrar después: (1) traducir `schema.sql` (`AUTOINCREMENT` → `GENERATED ALWAYS AS IDENTITY`,
`geometria_wkt` → `geometry(LineString, 4326)` con PostGIS); (2) implementar la rama `postgresql` de `conectar()`
con `psycopg`; (3) cambiar `VIA_VIVA_DB_URL` en `.env`. Las consultas usan `?`; `marcador()` da `%s` para PostgreSQL.

### Resultado de la prueba (2-nov-2026)

`db\reconstruir.ps1 -Limpiar` en una copia limpia (sin `.venv`, sin `data/`, sin `.env`), con Windows PowerShell 5:
terminó sin errores en **305 s** (incluye crear el entorno e instalar paquetes). Filas por tabla:

| Tabla | Filas |
|---|---|
| tramos | 5 775 |
| nodos | 4 054 |
| barrios | 154 |
| fuentes_externas | 150 (lluvia: 5 estaciones × 30 días) |
| variables_tramo | 5 775 |
| eventos, reportes, riesgo | 0 (se llenan con recorridos, el bot y el modelo) |
