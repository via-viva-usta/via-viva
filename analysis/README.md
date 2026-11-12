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

> **Histórico (3–7 nov).** La salida de campo vigente es `README_SALIDA.md` (roles del 11-nov: phyphox en el iPhone A
> de Anzola, captura y marcas en su Lenovo, Pipe solo video). Este protocolo con `captura_phyphox_remoto` queda como
> registro de los primeros recorridos.

### 1. Configurar phyphox (una vez)

1. phyphox → **+** → *Add simple experiment* → marcar **Accelerometer** (con g, NO "linear acceleration"),
   **Gyroscope** y **Location (GPS)**. Tasa: la máxima que permita el teléfono. Nombre: `VIA VIVA`.
   Teléfono del equipo: **iPhone 17 de Pipe (iOS)**: la tasa máxima real es **~100 Hz** (no 200); el análisis lo
   detecta solo y `herramientas.validar_campo` la mide en cada export.
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
| **1 minuto detenidos al inicio y 1 al final**, con *play* ya oprimido | Línea base, gravedad y cierre limpio |

**Cómo etiquetar — PLAN A (desde el 7-nov): captura en vivo por el acceso remoto de phyphox**

1. iPhone de Pipe: activar el **punto de acceso personal**; conectar el portátil a esa red.
2. phyphox → experimento **"VÍA VIVA 2.0"** → menú ⋮ → **Permitir acceso remoto**: anota la URL que muestra
   (con punto de acceso suele ser `http://172.20.10.1:8080`; usar la que diga phyphox).
3. En el portátil (copiloto):
   `dataset\.venv\Scripts\python -m herramientas.captura_phyphox_remoto --url http://172.20.10.1:8080 --nombre ruta1_pipe`
   y abrir la **vista en vivo** http://127.0.0.1:8090 (velocidad, aceleración, mapa y contador de eventos).
4. ▶ en phyphox. Cada vez que la llanta pasa por algo, el copiloto oprime en el PC: **H** hueco · **R** resalto ·
   **G** grieta · **T** tapa · **O** obstáculo · **I** impacto · **P** parada (inicio/fin) · **Q** terminar
   (o los botones de la vista en vivo). Se guarda la hora del PC, el tiempo del experimento y la posición GPS.
5. Si se cae el WiFi del iPhone, la herramienta pita, avisa y reconecta sola; los datos siguen en phyphox y se piden
   desde donde iban. Al final, **exportar también desde phyphox** (respaldo) y subir a Drive.
6. Queda `data/raw/phyphox/AAAA-MM-DD_HH-MM-SS_ruta1_pipe/` (mismo formato que el export de iOS) +
   `..._etiquetas.csv`: `validar_campo` y `etl.recorridos` lo leen sin cambios.

Demo sin carro: `--reproducir data\raw\phyphox\<export>.zip --velocidad 1` sirve una grabación como si fuera en vivo.
Probado el 7-nov con los 3 exports reales (01, 02, 03): la captura sale **idéntica** al export y pasa el validador;
falta probarla con el iPhone en el carro.

**PLAN B — cronómetro del iPhone por vueltas:**
1. El copiloto inicia el **cronómetro del iPhone en el mismo instante** en que se oprime *play* en phyphox.
2. Cada vez que la llanta pasa por un hueco, resalto, etc., oprime **"Vuelta"** y dice en voz alta la clase; el otro
   la anota en papel o en notas (vuelta 1 = hueco, vuelta 2 = resalto…).
3. Si el carro se detiene (semáforo, trancón), oprime "Vuelta" al parar (`parada_inicio`) y al arrancar (`parada_fin`):
   así no se buscan huecos con el carro quieto.
4. Al final, pasar a un `.txt` una línea por vuelta, **en orden (vuelta 1 primero)**, con la **duración que muestra el
   iPhone** (en iOS cada vuelta muestra su duración, no el acumulado) y la clase:

```text
1:02.40 hueco
0:33.10 resalto
0:20.00 parada_inicio
0:45.00 parada_fin
```

5. Convertir: `analysis\.venv\Scripts\python analysis\vueltas_a_etiquetas.py data\raw\phyphox\<recorrido>_vueltas.txt`
   → `<recorrido>_etiquetas.csv` (suma las duraciones; si se copió la lista con la vuelta más reciente arriba, `--invertir`).
   Ejemplo completo: `analysis/ejemplos/vueltas_ejemplo.txt`. Error aceptable: ±1 s.

### 3. Entregar los archivos

Se suben a Drive `VIA_VIVA/02_DATOS/phyphox/`; Andrés los baja a `data/raw/phyphox/` (ignorada por Git) y corre
`python -m herramientas.validar_campo` antes de analizarlos. Por cada recorrido:

| Archivo | Obligatorio | Contenido |
|---|---|---|
| `<recorrido>.zip` **o** `<recorrido>/` **o** `<recorrido>.csv` | Sí | Export de phyphox tal cual (zip, carpeta descomprimida o un solo CSV) |
| `<recorrido>_vueltas.txt` | Sí, si hubo etiquetado | Lo anotado del cronómetro (se convierte con `vueltas_a_etiquetas.py`) |
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

`t_s` = segundos desde que se oprimió *play* en phyphox. `clase` ∈ `hueco`, `resalto`, `impacto_fuerte`, `obstaculo`, `otro` (+ `parada_inicio` y `parada_fin`, que no son eventos).

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

## Cadena de entrenamiento del detector (un comando)

```powershell
analysis\.venv\Scripts\python analysis\entrenar_detector.py              # con los recorridos reales de data/raw/
analysis\.venv\Scripts\python analysis\entrenar_detector.py --sintetico  # prueba de la cadena con datos SINTÉTICOS
```

1. **Recorridos etiquetados**: phyphox (`data/raw/phyphox/`) y nodo (`data/raw/nodo/<sesión>/crudo_NNN.csv`,
   `gps_NNN.csv`, `etiquetas_NNN.csv`). Se necesitan ≥ 2 para validar.
2. **Señal igual a la del nodo**: \|a\| − 1 g a 200 Hz. Ventanas ancladas en el disparo del **detector por umbrales**
   (como en el ESP32); los disparos sin etiqueta son falsas alarmas (negativos difíciles) y hay ventanas normales al azar.
3. **Características** idénticas a `src/caracteristicas.h` (pico, RMS, curtosis, factor de cresta, jerk, signo) + velocidad.
4. **Modelos**: bosque aleatorio (10 árboles, profundidad ≤ 6) y red 1D (`modelo_cnn.py`, 788 parámetros) en float32 y
   **int8** (cuantización propia, idéntica en Python y en C).
5. **Validación leave-one-drive-out** por ventana (F1 macro y F1 de huecos) y **por evento** sobre todos los disparos:
   detector por umbrales solo vs. umbral + bosque vs. umbral + red int8 (precisión, recall, F1, falsos por km).
6. **Exportación a C**: `firmware/nodo-sensores/src/modelo_cnn.h` (float32 + int8) y `modelo_bosque.h` (emlearn).
   Métricas en `analysis/salidas/detector_<fecha>.md` (carpeta ignorada por Git).

**Estado (2-nov-2026):** probada solo con `--sintetico` (6 recorridos, 232 ventanas). Los modelos exportados hoy llevan
`MODELO_SINTETICO 1`: sirven para medir latencia en E2/E3, **no** para detectar huecos. Las métricas sintéticas salen
perfectas porque los datos falsos son fáciles: no son resultados. Con los recorridos reales basta volver a correr el comando.
