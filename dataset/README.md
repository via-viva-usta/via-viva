# dataset/ — dataset propio de fotos (celular) y clasificador de imágenes

Cambio de plan del 3-nov-2026: la evidencia visual la toma el **celular**. Cómo tomar las fotos: `docs/protocolo_fotos.md`.
Las fotos y sus metadatos viven en `data/` (**ignorada por Git**: nada de esto se sube).

```
Drive VIA_VIVA/02_DATOS/fotos/AAAA-MM-DD_nombre/  →  data/raw/fotos/  →  ingesta  →  data/procesado/{fotos/, metadatos.csv, calidad.csv, reporte_calidad.md}
                                                                   ↓ etiquetador (personas)
                                                    escala (tarjeta ArUco)  ·  modelo (MobileNetV3 → TFLite int8)
```

| Archivo | Qué hace |
|---|---|
| `comun.py` | Esquema del CSV, las 9 clases, valores válidos, rutas, `momento_dia` y agrupación por **sitio** |
| `tarjeta_aruco.py` | Genera `docs/tarjeta_aruco.pdf` (4 tarjetas de 10 × 10 cm por hoja carta, marcador de 80 mm, regla de 20 cm) |
| `ingesta.py` | EXIF (fecha, hora, GPS), tramo, barrio y tipo de vía (OSM), planilla, clima, difuminado, reporte de calidad |
| `planilla.py` | Lee los CSV de la planilla de campo y los une a las fotos por hora (± 5 min) y sitio |
| `etiquetador.py` | Página local con botones para etiquetar (sección 3) |
| `escala.py` | Tarjeta ArUco → homografía → vista cenital → área aproximada del daño; validación contra regla |
| `modelo.py` | Transfer learning, división por sitio, métricas, matriz de confusión, errores, TFLite int8 |
| `sintetico.py` | Fotos **SINTÉTICAS** para probar el flujo sin fotos reales (nunca son resultados) |

## 1. Instalación (una vez, en el PC de Andrés)

```powershell
py -3.11 -m venv dataset\.venv
dataset\.venv\Scripts\python -m pip install -r dataset\requirements.txt
# Modelo: TensorFlow no cabe en la ruta del repo (Windows sin rutas largas) → venv de ruta corta
py -3.11 -m venv $env:USERPROFILE\.venvs\vv-modelo
& $env:USERPROFILE\.venvs\vv-modelo\Scripts\python -m pip install -r dataset\requirements-modelo.txt
```

`opencv-contrib-python-headless` va fijo en `< 5` (la 5 ya no trae los clasificadores de caras y placas); `pandas==3.0.0`
y `tensorflow==2.20.0` porque **Smart App Control** de Windows bloquea pandas 3.1 y TensorFlow 2.21 (5-nov).

## 2. Ingesta

1. Descargar de Drive `VIA_VIVA/02_DATOS/fotos/AAAA-MM-DD_nombre` a `data\raw\fotos\` (sin cambiar los nombres) y
   los CSV de la planilla a `data\raw\planilla\`. Antes: `python -m herramientas.validar_campo` (revisión rápida).
2. Si hubo nodo encendido, copiar la microSD (`ambiente_NNN.csv`, etc.) a `data\raw\nodo\<fecha>\`.
3. Correr (desde `via-viva\`):

```powershell
$env:PYTHONIOENCODING="utf-8"
dataset\.venv\Scripts\python -m dataset.ingesta
```

Se puede repetir cada vez que lleguen fotos: **no pisa** lo que ya se etiquetó. Sin internet: `--sin-api`.
El resultado está en `data\procesado\reporte_calidad.md` (qué falta por clase, fotos sin GPS, borrosas, duplicadas).

**Clima (temperatura y humedad), en este orden:** lectura del termohigrómetro escrita en el etiquetador (se copia a
todas las fotos del sitio) → registro del nodo a ± 30 min → API histórica por hora de Open-Meteo para el centro de Tunja
(`fuente_clima = api`). `lluvia_ideam` = lluvia del día en la estación IDEAM más cercana (de la base; para fechas
nuevas, actualizar antes con `etl\.venv\Scripts\python -m etl.scraping.clima_ideam`).

**Privacidad:** las copias en `data\procesado\fotos\` salen **sin EXIF** y con caras y placas difuminadas. El detector
es automático (cascadas de Haar) y puede fallar; las caras exigen tono de piel para no borrar las cebras. Si en el
etiquetador se ve una persona o una placa: **Excluir**.

## 3. Etiquetador (para Pipe y Juan Diego)

```powershell
dataset\.venv\Scripts\python -m dataset.etiquetador                # todas las fotos
dataset\.venv\Scripts\python -m dataset.etiquetador --autor pipe   # solo las de una carpeta AAAA-MM-DD_pipe
```

Se abre el navegador en http://127.0.0.1:8765 (solo funciona en ese PC; cerrar con Ctrl+C en la consola).

| Qué marcar | Teclas | Notas |
|---|---|---|
| **Clase** (obligatoria) | `1`–`9` | hueco, resalto, grieta, parche, tapa, obstáculo, línea de carril, paso peatonal, vía buena |
| Severidad | `Q` `W` `E` | leve, media, alta — **solo** hueco, grieta, parche, tapa y obstáculo (criterios en el protocolo) |
| Ángulo | `A` `S` `D` `F` | contexto, frente, lado, cenital |
| Luz | `Z` `X` `C` `V` | sol, sombra, nublado, noche |
| Superficie mojada | `M` | alterna sí / no |
| Superficie | clic | asfalto, concreto, adoquín, destapada (si la planilla la trae ya viene marcada) |
| Guardar y seguir | `Enter` | guarda solo esa fila del CSV |
| Anterior / siguiente | `←` `→` | |
| **Excluir** | botón | persona o placa visible, foto inservible, o la foto del termohigrómetro |

Opcionales: distancia al daño (m), notas, **largo y ancho medidos con regla** (cm, validan la escala) y la lectura
del **termohigrómetro** (°C y % HR; escribirla en una foto del punto basta).

Recomendaciones: etiquetar **en un solo PC** a la vez (el CSV es uno); si dos personas etiquetan al tiempo, que cada una
use `--autor` con fotos distintas, en el mismo PC. Ante la duda entre dos clases, elegir la del daño y explicar en notas.
Ritmo esperado: 4–6 fotos por minuto con el teclado.

## 4. Escala con la tarjeta ArUco

```powershell
dataset\.venv\Scripts\python -m dataset.escala --validar
```

Usa las fotos con ángulo **cenital**. Escribe `data\procesado\escala.csv` (px/cm, inclinación, área, largo y ancho) y
las vistas rectificadas con el contorno en `data\procesado\rectificadas\`. `--validar` compara con las medidas con regla.
El área es **aproximada**: falla con sombras duras pegadas al daño, agua o daños que no son más oscuros que el asfalto.

## 5. Modelo

```powershell
& $env:USERPROFILE\.venvs\vv-modelo\Scripts\python -m dataset.modelo
```

Exige ≥ 3 sitios etiquetados por clase. Divide por **sitio** (nunca por foto), entrena MobileNetV3-Small y deja todo en
`data\procesado\modelo\<versión>\`: `reporte.md`, `metricas.json`, `matriz_confusion.png`, `errores.png`,
`division.csv`, `modelo.keras`, `modelo_float32.tflite`, `modelo_int8.tflite`, `etiquetas.txt`.

## 6. Prueba con datos sintéticos (lo que se hizo el 3-nov)

```powershell
dataset\.venv\Scripts\python -m dataset.sintetico               # 432 fotos: 12 sitios × 9 clases × 4 ángulos
dataset\.venv\Scripts\python -m dataset.ingesta --sintetico
dataset\.venv\Scripts\python -m dataset.sintetico --etiquetar   # etiquetas verdaderas
dataset\.venv\Scripts\python -m dataset.escala --sintetico --validar
& $env:USERPROFILE\.venvs\vv-modelo\Scripts\python -m dataset.modelo --sintetico
```

Todo va a `data\raw\fotos_sintetico\` y `data\procesado_sintetico\` (nunca se mezcla con lo real) y queda marcado
SINTÉTICO. Lo que mostró (solo prueba del flujo, **no son resultados**): tarjeta hallada en 105 de 108 cenitales; área
con mediana de error −17 % frente al área dibujada; modelo float 0,98 e int8 0,81 de exactitud en test (la
cuantización post-entrenamiento pierde exactitud: hay que medirla con las fotos reales).
