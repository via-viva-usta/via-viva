# data/

Aquí **solo** van muestras pequeñas y anonimizadas (por ejemplo `data/muestras/`).

| Carpeta | ¿Se sube? | Contenido |
|---|---|---|
| `raw/` | **No** (ignorada) | Recorridos crudos (phyphox, nodo) |
| `alcaldia/` | **No** (ignorada) | Datos de la Alcaldía / Tránsito; no se publican sin permiso |
| `osm/` | **No** (ignorada, se regenera) | Grafo de Tunja descargado por `etl/` |
| `campo/` | **No** (ignorada) | Listas de visita y revisiones de campo (`tramos_revisados.csv`) del modelo de riesgo |
| `muestras/` | Sí | Muestras pequeñas sin datos personales |

Los datos crudos se comparten por la carpeta compartida del equipo, no por Git.
Nunca guardar trayectorias completas de conductores en la base final: solo eventos.

**Estado:** vacía.
