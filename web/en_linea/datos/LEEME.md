# Datos del tablero en línea

| Archivo | Qué es | Fuente y licencia |
|---|---|---|
| `tramos.geojson` | Las calles de Tunja como tramos (`id`, nombre `n`, tipo de vía `t`, barrio o vereda `b`, largo `l` en m). La web cruza `id` con el `id_tramo` de los huecos que suben de la Pi, así que debe salir de la **misma base** que usa la Pi | Calles: © OpenStreetMap contributors, **ODbL 1.0** (https://www.openstreetmap.org/copyright). Barrio de cada tramo: datos.gov.co, conjunto 4ryc-k7fx (licencia por confirmar; ver `ATRIBUCIONES.md`) |

Este archivo es una **base de datos derivada de OpenStreetMap**: si se comparte o se modifica, sigue bajo ODbL y debe
mantener la atribución. Se regenera con `viaviva nube preparar` (`viaviva/nube.py`). No contiene huecos, recorridos ni
datos personales.
