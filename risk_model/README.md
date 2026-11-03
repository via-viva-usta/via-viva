# risk_model/

Modelo predictivo georreferenciado: probabilidad de que un tramo de calle (OpenStreetMap) tenga huecos
**aún no reportados**. Regresión logística y bosque aleatorio, con **validación espacial por barrios**.

Usa el entorno de `etl/` (`risk_model/requirements.txt` agrega scikit-learn). Todo se corre desde `via-viva/`.

## Flujo

```powershell
etl\.venv\Scripts\python -m etl.osm_tunja          # tramos y nodos (Fase 1)
etl\.venv\Scripts\python -m etl.scraping.clima_ideam
etl\.venv\Scripts\python -m etl.barrios_tunja      # 154 barrios y veredas (Alcaldía, datos abiertos)
etl\.venv\Scripts\python -m etl.elevacion          # elevación de nodos (SRTM 30 m) y pendiente por tramo
etl\.venv\Scripts\python -m risk_model.variables   # tabla variables_tramo
etl\.venv\Scripts\python -m risk_model.modelo --guardar --lista-campo
```

## Tabla de variables por tramo (`variables_tramo`)

| Variable | Fuente | Cómo se calcula |
|---|---|---|
| `tipo_via` | OSM `highway` | Agrupado: trunk, primary, secondary, tertiary, unclassified, residential, otro (`*_link` → su vía) |
| `clase_superficie` | OSM `surface` | pavimentada / sin_pavimentar / desconocida |
| `longitud_m` | osmnx | Longitud del tramo |
| `pendiente_pct` | SRTM 30 m (OpenTopoData) | \|elev(u) − elev(v)\| / longitud. NULL en tramos < 30 m (el DEM no los resuelve) |
| `lluvia_30d_mm`, `lluvia_max_dia_mm` | IDEAM (datos.gov.co) | Por estación, suma y máximo diario de los últimos 30 días; al tramo por distancia inversa (IDW, potencia 2) |
| `huecos_vecinos` | Nodo + ciudadanos + inventario Alcaldía | Huecos conocidos a ≤ 300 m **en otros tramos** (el propio se excluye para no filtrar la etiqueta) |
| `accidentes_cercanos` | `data/alcaldia/siniestros.csv` + noticias con coordenadas | Siniestros a ≤ 200 m |
| `rugosidad_media`, `profundidad_max_mm` | Eventos del nodo | Promedio / máximo de los eventos asignados al tramo (≤ 30 m) |
| `barrio`, `sector` | Alcaldía (datos abiertos `4ryc-k7fx`) | Barrio cuyo punto de referencia está más cerca del centro del tramo |
| `etiqueta` | Huecos conocidos + revisiones de campo | 1 = hueco confirmado; 0 = revisado sin hueco; NULL = no se sabe |

### Archivos que el equipo debe aportar (no se suben a Git)

| Archivo | Columnas | Para qué |
|---|---|---|
| `data/alcaldia/huecos.csv` | `lat, lon` (o `latitud, longitud`) | Inventario de huecos de la Secretaría de Infraestructura → etiquetas 1 y `huecos_vecinos` |
| `data/alcaldia/siniestros.csv` | `lat, lon` | Siniestros georreferenciados de Tránsito → `accidentes_cercanos` |
| `data/campo/tramos_revisados.csv` | `id_tramo, tiene_hueco` (0/1) | Revisiones de campo → **las etiquetas 0** (sin ellas el modelo no tiene negativos) |

Los eventos del nodo y los reportes del bot entran solos desde la base.

## Modelos y validación (`modelo.py`)

- **Regresión logística** (one-hot + estandarización, `class_weight="balanced"`) y **bosque aleatorio** (300 árboles).
- **Validación espacial:** `GroupKFold` con el barrio como grupo → cada pliegue deja fuera barrios **completos**.
  `--grupo sector` deja fuera sectores enteros (más estricto).
- Se reporta también la AUC con pliegues al azar solo para mostrar cuánto se infla; la del informe es la espacial (meta ≥ 0,70).
- `--guardar` escribe la tabla `riesgo` (probabilidad y rango por tramo, con las variables en JSON para explicar cada valor).
- `--lista-campo` genera `data/campo/visita_<fecha>.csv`: **10 tramos de mayor riesgo no reportados + 10 al azar**, con
  una columna `tiene_hueco` para llenar en la visita. Esa es la métrica central del proyecto.
- Requisitos mínimos para entrenar: 30 tramos etiquetados, 5 de cada clase y 3 barrios. Si no se cumplen, el script
  se detiene y dice qué falta.

## Estado (26-oct-2026)

Calculado con código sobre los datos reales disponibles hoy:

| Dato | Valor |
|---|---|
| Tramos con variables | 5 775 |
| Tramos con pendiente | 4 659 (elevación de nodos de 2 492 a 3 202 m; mediana de pendiente 4,8 %, p90 13,7 %) |
| Superficie conocida en OSM | 633 tramos (455 pavimentados, 178 sin pavimentar); 5 142 desconocida |
| Lluvia 30 días interpolada | 80,8 a 108,4 mm (5 estaciones IDEAM) |
| Barrios asignados | 152 de 154 (distancia mediana del tramo al punto del barrio: 148 m) |
| Huecos conocidos | **0** |
| Tramos etiquetados | **0** → **no se puede entrenar con datos reales todavía** |

`--demo-sintetico` inventa etiquetas con una fórmula (pendiente, superficie, tipo de vía, lluvia y un efecto por barrio)
solo para comprobar que el flujo completo corre. **Sus métricas no son resultados** y el script lo imprime en un recuadro.
Hoy la tabla `riesgo` de la base local tiene una corrida `DEMO-SINTETICO` para que el tablero tenga algo que dibujar; el
tablero la muestra con un aviso rojo. Al entrenar con datos reales se agrega una corrida nueva con otra versión.

## Limitaciones conocidas

- Los barrios de la Alcaldía son **puntos**, no polígonos: el barrio de cada tramo es una aproximación (vecino más cercano).
  Si se consiguen los polígonos de barrios o comunas, reemplazar `asignar_barrio`.
- Con 5 estaciones la lluvia cambia poco dentro de la ciudad; aportará más cuando se cruce con la fecha de aparición de huecos.
- SRTM tiene error vertical de varios metros: la pendiente de tramos cortos es ruidosa.
- Solo el 11 % de los tramos tiene superficie en OSM.

## Plan B: entrenar sin datos de la Alcaldía (decisión del 2-nov)

Si la Alcaldía no entrega su inventario antes del **9-nov**, el modelo se entrena con lo que produce el propio equipo:

| Fuente | Aporta | De dónde |
|---|---|---|
| `recorrido` | 1 y **0** (tramos revisados con y sin hueco) | `etl.recorridos` → `data/campo/tramos_revisados.csv` |
| `visita` | 1 y 0 | Visitas de campo → `data/campo/tramos_revisados_visita_<fecha>.csv` |
| `bot` | 1 | Reportes ciudadanos de hueco (no descartados) |
| `nodo` | 1 | Eventos `hueco` del nodo |
| `alcaldia` | 1 | `data/alcaldia/huecos.csv` |

`variables_tramo.fuente_etiqueta` guarda todas las fuentes de cada etiqueta (p. ej. `bot;recorrido`).

```powershell
etl\.venv\Scripts\python -m etl.recorridos                 # recorridos etiquetados → tramos revisados
etl\.venv\Scripts\python -m risk_model.variables
etl\.venv\Scripts\python -m risk_model.modelo --fuente auto --guardar --lista-campo
```

`--fuente auto` usa `alcaldia` si hay datos de la Alcaldía y si no `planb`; también se puede forzar `alcaldia`, `planb`
o `todas`. **Cada corrida registra la fuente** en `riesgo.fuente_etiquetas` (p. ej.
`planb: bot+recorrido (n=134, con hueco=29)`) y en la versión (`v0.1-<fecha>-planb`). El tablero y el mapa web la muestran.

**Prueba del 2-nov (base temporal, NO resultado):** con los 3 recorridos sintéticos y 3 reportes de prueba, `auto`
eligió `planb`, entrenó con 134 tramos (29 con hueco) y guardó la corrida con su fuente. La AUC espacial salió ≈ 0,5,
lo esperado porque en los datos sintéticos los huecos se ponen al azar (sirve también de control: no hay fuga de la
etiqueta hacia las variables). Con la base real hoy se detiene: hay 0 etiquetas.
