# Detectores: fuentes externas, factores excluidos y plan de unificación (19-nov-2026)

Esta revisión es de solo lectura: no se descargó, instaló ni incorporó nada. Las licencias se leyeron en la página o en
el `LICENSE` de origen. Si algo no se pudo confirmar, dice «no verificado».

## 1. Datasets y métodos externos

Ningún dataset encontrado es SINTÉTICO. Ninguno separa tapa, grieta y parche. Lo habitual es «hueco + grieta»,
«resalto» y «vía lisa».

| Candidato | Datos / fs / unidades | Licencia | Compatibilidad con VÍA VIVA | Recomendación |
|---|---|---|---|---|
| [PVS](https://github.com/jefmenegazzo/Intelligent-Vehicle-Perception-Based-on-Inertial-Sensing-and-Artificial-Intelligence): 9 sesiones, 3 carros y 3 conductores, ~108 km | MPU-9250 a 100 Hz en m/s², GPS a 1 Hz, video. Etiquetas: superficie, rugosidad y resalto (sin hueco) | CC BY-NC-ND 4.0 | Alta para el MPU del tablero. Sirve para resalto frente a vía buena y para ver la generalización entre carros. ND: no se redistribuyen derivados | **Evaluar** (con aprobación) |
| [Mendeley 4hmyws7cbc](https://data.mendeley.com/datasets/4hmyws7cbc/1) | iPhone a 100 Hz en un bus, GPS a 1 Hz. Huecos y resaltos por inspección con fotos | CC BY 4.0 | Mismo formato que phyphox. El montaje en bus responde distinto | **Evaluar**, tras revisar los archivos |
| [RSC-IoT](https://ieee-dataport.org/documents/rsc-iot-iot-based-dataset-road-anomaly-detection-using-motion-sensors) / [RSC](https://ieee-dataport.org/documents/rsc-dataset-smartphone-based-sensor-data-road-surface-condition-monitoring) | RSC-IoT usa el **MPU-6050** en el tablero. Clases: hueco + grieta, resalto, liso. fs no indicada | CC BY 4.0; requieren suscripción a IEEE DataPort | Muy alta en sensor | Evaluar si la universidad tiene acceso |
| [CRAWDAD JIIT](https://ieee-dataport.org/open-access/crawdad-jiitaccelerometer): 678 km, 22 conductores | Acelerómetro Android; resaltos marcados con botón | CC BY 4.0, acceso abierto | Su marcado se parece al nuestro. Hay que reorientar los ejes y deducir la fs | Evaluar la exhaustividad en resaltos |
| [Mendeley 92yrxtv5gn](https://data.mendeley.com/datasets/92yrxtv5gn/1) | Buses en India, m/s². Los autores lo advierten ruidoso | CC BY 4.0 | Baja | Referencia |
| [warstad11/pothole](https://github.com/warstad11/pothole) | Random forest, 1D-CNN y BiLSTM sobre el IMU | MIT | Su lección importa: la precisión cayó a ~0,10 en la calle | Referencia |
| Pothole Patrol (Eriksson 2008, [PDF](https://people.cs.rutgers.edu/~badri/553dir/papers/sensor/mobisys08.pdf)) | Filtros: velocidad → pasa-altos → pico z → razón x/z → velocidad/z. 380 Hz | Artículo | Se implementa en numpy y corre en la Pi | **Línea base** |
| Mednis et al. 2011 (doi 10.1109/DCOSS.2011.5982206) | Z-THRESH, Z-DIFF, STDEV(Z), G-ZERO | Artículo | Triviales en numpy. Umbrales del artículo no verificados | **Línea base** del detector en vivo |
| González et al. 2017 (doi 10.1109/TITS.2017.2662483) | Bag-of-words sobre la aceleración; compara ANN, árbol de decisión y SVM | Artículo | Fuera de línea, en el PC | Referencia |

**Segunda revisión (19-nov, tarde).** Solo lectura: no se descargó nada y no se inició sesión. **PVS ya se evaluó
localmente**; su informe está en `C:\VIA_VIVA_DATOS\PVS_evaluacion\INFORME.md`, fuera de Git.

| Fuente | Datos | Licencia y acceso | Decisión |
|---|---|---|---|
| [Mendeley 4hmyws7cbc](https://data.mendeley.com/datasets/4hmyws7cbc/1) | iPhone 11 y 13 bajo un asiento de bus, a 100 Hz, con GPS a 1 Hz. Etiquetas manuales con fotos. ~113 MB | Datos CC BY 4.0; descarga pública sin cuenta | **Usar** (detección de «anomalía sí/no»). Antes hay que confirmar columnas, unidades y clases, que no se pudieron ver |
| [RoadSens-4M](https://doi.org/10.6084/m9.figshare.30341143.v3) | Samsung S24 en el parabrisas con ejes alineados al carro, en m/s² a 100 Hz. Clases bump, pothole y normal, marcadas con botón (50 eventos validados con video). ~297 MB en Figshare; el crudo y los videos están en Drive | Datos CC BY 4.0 en Figshare; el artículo es CC BY-NC-ND; el código MIT | **Usar** como referencia principal para hueco, resalto y vía buena |
| [CRAWDAD JIIT](https://ieee-dataport.org/open-access/crawdad-jiitaccelerometer) | Android, 678 km, resaltos. fs y unidades no indicadas. ~46 MB | CC BY 4.0. crawdad.org responde 404; IEEE pide cuenta | Evaluar luego |
| [RSC-IoT](https://ieee-dataport.org/documents/rsc-iot-iot-based-dataset-road-anomaly-detection-using-motion-sensors) | MPU-6050 en el tablero. Hueco y grieta van juntos. 1,1 MB | CC BY 4.0, **pide suscripción a IEEE DataPort** | Evaluar si hay acceso institucional |
| [RDD2022](https://github.com/sekilab/RoadDamageDetector) | **Solo imágenes**: grietas D00/D10/D20 y bache D40. Hay subconjuntos por país (Chequia 245 MB, EE. UU. 424 MB) | Imágenes CC BY-SA 4.0; código MIT; licencia de los pesos no indicada | Evaluar luego, para la evidencia fotográfica. No sirve para el acelerómetro |
| [GOV.CO v5](https://cdn.www.gov.co/v5/) | Componentes de sedes oficiales. La página carga con JavaScript; se leyó el Anexo 2.1 de la Res. 2893/2020 | Obligatorio solo para entidades públicas | Tomar patrones (accesibilidad WCAG 2.1 AA, migas, filtros con contador, pie de atención). **No** usar las barras ni el logo de GOV.CO ni de la Alcaldía: el prototipo parecería un servicio oficial |

**Skills y plugins de Claude Code:**
- [anthropics/skills](https://github.com/anthropics/skills) (Apache-2.0): xlsx, pdf y skill-creator ya están
  disponibles en la sesión.
- [claude-plugins-official](https://github.com/anthropics/claude-plugins-official) trae commit-commands y
  pr-review-toolkit. Se solapan con `/code-review`.
- [K-Dense scientific skills](https://github.com/K-Dense-AI/claude-scientific-skills) (MIT) se solapa con el análisis
  genérico.
- No hay un skill de Raspberry Pi mantenido y de fuente confiable.
- **Propuesta:** no instalar nada externo por ahora y usar las skills del proyecto (`.claude/skills/vv-*`).

## 2. Factores excluidos: ¿conviene recuperarlos?

| Factor | Por qué salió | ¿Se puede medir? | Valor si vuelve | Costo y riesgo | Propuesta |
|---|---|---|---|---|---|
| Velocidad del carro (OBD2, solo lectura) | Opcional, sin código (`futuro/`) | Sí, con ELM327 (PID 010D) | Respaldo del GPS a baja velocidad, que es donde el detector se apaga (< 5 km/h) | Un adaptador Bluetooth; nunca escribir en la ECU | Después, si el GPS falla en la prueba |
| Distancia a la vía (VL53L0X) | Ya está en la Pi como sensor opcional | Sí. **No probado** | Profundidad o altura de resaltos | Ruido por vibración y luz solar | Registrar y comparar con las marcas antes de usarlo |
| Luz (BH1750) y clima (DHT22) | En la Pi como contexto | Sí. **No probado** | Contexto: noche o lluvia cambian la visibilidad del copiloto que marca | Bajo | Solo contexto; no entra al detector |
| Lluvia IDEAM y pendiente SRTM | Están en el modelo de **riesgo**, no en el detector | Sí (5 estaciones; SRTM ruidoso en tramos cortos) | Riesgo por tramo | Ya implementado | Mantener donde está |
| Cámara del nodo (ESP32-CAM) | 3-nov: el celular toma mejor evidencia | Sí | Verificar eventos | Corriente, cableado, privacidad | No; el video del iPhone B basta |
| Láser de cuadrícula (profundidad) | No se consiguió | — | Profundidad del hueco | Hardware nuevo | No por ahora; la escala sale de la tarjeta ArUco |
| Reportes ciudadanos y bot de Telegram | Fuera del alcance desde el 13-nov | Sí | Etiquetas positivas de hueco | Spam y moderación; datos personales | No para el detector |
| Tipo y superficie de vía (OSM) | Ya en el riesgo; solo el 11 % de tramos tiene superficie | Parcial | Normalizar umbrales por tipo de vía | Pocos datos | Usar para **estratificar** la evaluación, no para fijar umbrales |
| Multas, placas, conductores | Excluido por diseño | — | — | Privacidad | Se mantiene fuera |

## 3. Flujo común para comparar y unificar

1. **Un solo formato de entrada:** la carpeta de sesión de la app (phyphox o Pi), con `Accelerometer*.csv`,
   `Location.csv` y las marcas vigentes. Los exports de phyphox también se aceptan.
2. **Auditoría primero:** `herramientas/auditar_sesion.py`. Una sesión con FALLA de hora o de huecos no entra a la
   comparación sin anotarla.
3. **Los dos detectores con la misma señal:** `herramientas/comparar_detectores.py`.
   - Misma tolerancia (`tolerancia_s`), mismas clases positivas y mismas marcas para ambos.
   - El detector en vivo se repite muestra a muestra, y debe reproducir `eventos.csv` (`repeticion_fiel`).
   - Con la Pi, `--sensor adxl2|mpu6050` muestra si los sensores discrepan.
4. **Revisión visual:** el HTML pone, en el mismo eje de tiempo, la señal de cada detector, la velocidad, las marcas por
   clase y los eventos de cada uno. Las etiquetas se corrigen con el video en **Revisión**.
5. **Umbrales solo con datos:**
   - ≥ 2 salidas reales con marcas revisadas;
   - calibración dejando una salida afuera;
   - margen elegido en la curva P/R de validación;
   - informar el intervalo y el número de marcas.
6. **Salida coherente al unificar:** el software sigue recibiendo un solo evento con `t_s`, `ts_utc`, `p2p_g`,
   `severidad`, `confianza` y `clase`. Se agrega quién lo disparó: en vivo, análisis o ambos. Si los sensores no
   coinciden, se marca `discrepancia` en lugar de ocultarlo.

**Medido hasta hoy** (umbrales actuales, sin calibrar; tolerancia ±1,5 s):

Sesión del 18-nov (69 marcas sin revisar):

| Detector | Eventos | TP | P | R |
|---|---|---|---|---|
| En vivo | 74 | 12 | 0,16 | 0,18 |
| Análisis | 8 | 2 | 0,25 | 0,03 |

- 7 eventos del detector de análisis coinciden con eventos del detector en vivo.
- La repetición del detector en vivo reprodujo los 74 eventos de `eventos.csv`.

Exports del 7-nov (sin marcas):

| Export | En vivo | Análisis | Coinciden |
|---|---|---|---|
| 1 | 4 | 4 | 0 |
| 2 | 11 | 11 | 4 |
| 3 | 81 | 28 | 23 |

Estas cifras **no** son una evaluación válida: las marcas tienen baja calidad y es una sola salida.
