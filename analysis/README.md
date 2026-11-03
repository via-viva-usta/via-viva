# analysis/

Señales de los recorridos: phyphox (celular) ahora, CSV del nodo después.

| Archivo | Qué es |
|---|---|
| `senales.py` | Funciones: lectura de phyphox, remuestreo, eje vertical, filtro, espectro y elección de fs, ventanas por energía/jerk, características, clasificador leave-one-drive-out, generador de datos sintéticos |
| `01_phyphox_clasificador.ipynb` | Notebook que usa esas funciones y grafica cada paso |

## Instalación (una vez, desde `via-viva/`)

```powershell
py -3.11 -m venv analysis\.venv
analysis\.venv\Scripts\python -m pip install -r analysis\requirements.txt
```

Abrir el notebook en VS Code (extensión Jupyter) y elegir el intérprete `analysis\.venv`.
No se usa JupyterLab: en Windows sin rutas largas activadas su instalación falla.

## Protocolo de recorridos con phyphox (para Pipe)

### 1. Configurar phyphox (una vez)

1. phyphox → **+** → *Add simple experiment* → marcar **Accelerometer** (con g, NO "linear acceleration"),
   **Gyroscope** y **Location (GPS)**. Tasa: la máxima que permita el teléfono. Nombre: `VIA VIVA`.
2. Ajustes del teléfono: GPS en alta precisión, ahorro de batería apagado, pantalla siempre encendida.
3. Probar en la casa: 1 minuto quieto → exportar → revisar que salgan `Accelerometer.csv`, `Gyroscope.csv`
   y `Location.csv` (la ubicación bajo techo puede salir vacía: es normal).

### 2. En el carro

| Regla | Por qué |
|---|---|
| Celular **fijo** en un soporte rígido (no en la mano, no suelto en la consola) | Si se mueve, la vibración ya no es la de la vía |
| Siempre en la **misma posición** y orientación en todos los recorridos | Para comparar recorridos |
| **Máximo 30 km/h**, conducción normal | Seguridad y comparabilidad (decisión del 2-nov) |
| Esperar fijación GPS (≥ 6 satélites) antes de *play* | Sin GPS no hay map-matching |
| El **copiloto** etiqueta; el conductor solo conduce | Seguridad |
| 1 minuto detenidos al inicio, con *play* ya oprimido | Línea base y estimación de la gravedad |

**Cómo etiquetar:** phyphox muestra el tiempo del experimento en pantalla. El copiloto lleva un cronómetro o anota el
tiempo de phyphox **en el instante** en que la llanta pasa por el hueco o el resalto, y la clase. Al final se transcribe
a `<recorrido>_etiquetas.csv`. Error aceptable: ±1 s (el procesamiento busca el candidato más cercano en ±1 s).

### 3. Entregar los archivos

Todo va en `data/raw/phyphox/` (ignorada por Git; se comparte por la carpeta del equipo). Por cada recorrido:

| Archivo | Obligatorio | Contenido |
|---|---|---|
| `<recorrido>.zip` **o** `<recorrido>/` **o** `<recorrido>.csv` | Sí | Export de phyphox tal cual (zip, carpeta descomprimida o un solo CSV) |
| `<recorrido>_etiquetas.csv` | Para entrenar y para el modelo de riesgo | Columnas `t_s,clase` (ver ejemplo) |

Nombre sugerido: `2026-11-03_ruta1_pipe` (fecha, ruta, quién). Ejemplo de `2026-11-03_ruta1_pipe_etiquetas.csv`:

```csv
t_s,clase
62.4,hueco
95.1,resalto
130.8,hueco
171.0,impacto_fuerte
240.2,otro
```

`t_s` = segundos desde que se oprimió *play* en phyphox. `clase` ∈ `hueco`, `resalto`, `impacto_fuerte`, `otro`.

### 4. Procesar

```powershell
etl\.venv\Scripts\python -m etl.recorridos          # pre-etiquetas, tramos revisados y eventos a la base
```

Sale `data/campo/preetiquetas_<recorrido>.csv` (candidatos del **detector por umbrales**, con la etiqueta del copiloto al
lado: sirve para revisar y corregir) y `data/campo/tramos_revisados.csv` (entrada del modelo de riesgo, plan B).
Con los datos en su sitio, el notebook también los detecta solo:

```python
from senales import procesar_carpeta
r = procesar_carpeta("../data/raw/phyphox")   # recorridos, ventanas y (si hay ≥2 etiquetados) modelos
```

### Prueba con datos sintéticos

`python -m etl.recorrido_sintetico --n 3` genera recorridos **SINTÉTICOS** en formato phyphox sobre calles reales de
Tunja (en `data/raw/phyphox_sintetico/`, nunca en la carpeta real). Prueba del 2-nov (solo prueba el software):
3 recorridos de ~3 km; 434/434, 473/473 y 422/422 fijaciones GPS asignadas a tramos; de 29 tramos con hueco puesto, 28 quedaron
marcados con hueco y 26 coinciden (las diferencias son por el ruido del GPS cerca de intersecciones: el map-matching es
por vecino más cercano). Estos números no describen las vías de Tunja.

## Qué hace cada paso

1. **Remuestreo** a una rejilla uniforme (phyphox no muestrea parejo); fs de trabajo = min(200 Hz, fs del teléfono).
2. **Eje vertical:** gravedad estimada con pasa-bajos de 0,3 Hz; la parte dinámica se proyecta sobre ella (no importa cómo esté puesto el celular).
3. **Espectro (Welch)** de la señal sin filtrar: frecuencia con el 95 % de la energía → fs mínima (Nyquist, 2×) y recomendada (2,5×).
4. **Filtro** Butterworth pasa-bajos de orden 4, fase cero, a min(80 Hz, 0,4·fs).
5. **Ventanas** de 1 s centradas en el pico donde la energía de 0,25 s o el jerk superan 4× su mediana; más ventanas "normales" al azar lejos de los eventos.
6. **Características:** pico, RMS, curtosis, factor de cresta, jerk máximo, signo del pico, asimetría, energía relativa por banda (0,5–5, 5–15, 15–30, 30–80 Hz) y pico/RMS divididos por la velocidad del GPS.
7. **Etiquetas:** cada etiqueta se asigna a la ventana detectada más cercana (≤ 1 s). Las detecciones sin etiqueta cuentan como `normal` (falsas alarmas).
8. **Clasificador:** bosque aleatorio y árbol de profundidad 4 (exportable a C), validados **dejando un recorrido fuera** (nunca por ventana). Métricas: F1 macro, F1 de huecos, matriz de confusión.

## Estado (26-oct-2026)

- El notebook **corre completo sin errores**, pero solo se ha probado con **datos sintéticos** (no hay recorridos reales todavía).
- El lector se probó con exports simulados en los tres formatos (carpeta con `Accelerometer.csv` + `Location.csv`, zip con
  `meta/`, y un CSV con `;` y coma decimal). **Falta probarlo con un export real de phyphox**: si los nombres de columna de su
  versión cambian, se ajustan los patrones en `_separar()`.
- Con los sintéticos el F1 sale ≈ 1,0: es porque los datos falsos son muy fáciles, **no es un resultado**. El notebook lo
  avisa en cada salida. El repositorio guarda el notebook **sin salidas** para que no se confundan con resultados.

## Pendiente

- Correrlo con los primeros recorridos reales y fijar fs.
- Leer los CSV del nodo (`crudo_NNN.csv` en cuentas de 3,9 mg, `gps_NNN.csv`, `etiquetas_NNN.csv`).
- Exportar el árbol a C / CNN 1D int8 para el experimento E3.
