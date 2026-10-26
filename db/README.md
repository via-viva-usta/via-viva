# db/

Esquema de la base de datos SQLite del servidor: `schema.sql`
(tablas `tramos`, `eventos`, `reportes`, `fuentes_externas`, `riesgo`; diagrama en `docs/diagramas/03_entidad_relacion.md`).

Crear la base: `etl\.venv\Scripts\python -m etl.db` (o `sqlite3 data/via_viva.db < db/schema.sql`).
El archivo `.db` se genera localmente y **no** se sube al repositorio.

**Estado:** esquema listo y probado (se crea sin errores y ya recibe `tramos` y `fuentes_externas` del ETL).
Pendiente: tabla `peligros` cuando exista la deduplicación.
