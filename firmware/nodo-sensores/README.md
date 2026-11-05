# firmware/nodo-sensores

Proyecto PlatformIO (framework Arduino sobre ESP-IDF) para la **ESP32 DevKit V1 de 30 pines (WROOM-32, entorno `esp32dev`)**:
4 MB de flash, 520 KB de SRAM, sin PSRAM. Pines en `include/pines.h` (sección 6 de `CLAUDE.md`); conexiones, alimentación,
orden de prueba y fallas típicas en `docs/montaje.md`.

> **Cambio de placa (2-nov-2026):** antes era una ESP32-S3. Cambió: pines, buses (VSPI para el ADXL345, HSPI por la
> matriz GPIO para la microSD), UART2 para el GPS, sin PSRAM. E2 = flash vs. SRAM; E3 = float32 vs. int8.
> **3-nov:** sin ESP32-CAM (código en `futuro/`); temperatura y humedad con **DHT22** en GPIO 25 (el código también acepta
> un BME280, que no se compró).

## Qué hace

| Pieza | Cómo | Archivo |
|---|---|---|
| ADXL345 por VSPI | Controlador propio a nivel de registros con el driver `spi_master` de ESP-IDF (DMA). FIFO en modo *stream* con watermark 31 → INT1 (GPIO 34) → lote por DMA → búfer **ping-pong** | `adxl345.*`, `adquisicion.cpp` |
| **Detector por umbrales** (línea base del docente) | Evento si velocidad GPS > V_min **y** el cambio de aceleración vertical en 50 ms supera K × la vibración de fondo de esa calle (y un piso absoluto). Por defecto `include/config.h`; **K, piso, V_min y refractario se ajustan desde la página** y quedan en la flash. La misma regla en Python (`analysis/detector_umbral.py`) pre-etiqueta los recorridos | `detector_umbral.h`, `ajustes.*`, `procesamiento.cpp` |
| **Maniobras** con el giroscopio del MPU-6050 | Giro a la izquierda / derecha (velocidad angular vertical) y frenada brusca (aceleración longitudinal o caída de velocidad GPS). Cada maniobra queda como evento propio, y un golpe que cae durante una maniobra se atribuye a ella y no a la vía | `maniobras.h`, `perifericos.cpp` |
| **Página web del nodo** (punto de acceso Wi-Fi) | Para el celular del copiloto: botones **Hueco / Resalto / Otro**, **gráfica en vivo** de \|a\| − 1 g, último evento, velocidad, ambiente, estado de la microSD y del GPS, **umbrales del detector** y **descarga de los CSV** sin sacar la tarjeta. Sin librerías externas (el celular no tiene internet en esa red) | `servidor_web.cpp`, `senal_vivo.h` |
| Ventana y características | Búfer circular de 2 s; pico, RMS, curtosis, factor de cresta, jerk; clase **provisional** por reglas hasta tener el modelo | `bufer_circular.h`, `caracteristicas.h` |
| MPU-6050 y VL53L0X por I2C | MPU con controlador propio (se mide su duración para E4); VL53L0X con la librería de Pololu | `mpu6050.h`, `perifericos.cpp` |
| GPS NEO-6M por UART2 | TinyGPSPlus; hora UTC de la fijación + `esp_timer` de llegada para interpolar en el ETL. Reinicia la UART si no llegan datos | `perifericos.cpp` |
| microSD por HSPI | Por sesión: `crudo_NNN.csv`, `eventos_NNN.csv`, `gps_NNN.csv`, `etiquetas_NNN.csv` (tipo y origen: web o botón), `ambiente_NNN.csv`, `exp_NNN.csv`. Número de sesión en la flash; reintentos y remontaje | `registro.cpp` |
| **Ambiente** (3-nov) | **DHT22 en GPIO 25** (o un BME280 en 0x76/0x77 si algún día se pone; si es BMP280 no hay humedad) y BH1750 (0x23). Cada `PERIODO_AMBIENTE_MS` (10 s) en la misma tarea I2C → `ambiente_NNN.csv` con hora UTC del GPS (`utc_fix` + `ms_desde_fix`), lugar, temperatura, humedad, presión y lux; también en la página web. Sirve para llenar el clima del dataset de fotos (`dataset/`) | `include/ambiente.h`, `perifericos.cpp` |
| **Robustez** (5-nov) | Watchdog de tareas, reintentos del GPS y de la microSD, causa del último reinicio, **LED con códigos de estado** | `registro.cpp`, `perifericos.cpp`, `led_estado.cpp`, `main.cpp` |
| **Experimentos E1–E4** | E1 por entorno (polling / interrupción / FIFO+DMA), cada 5 s; E2 (flash vs. SRAM), E3 (float32 vs. int8 y bosque) y E4 (I2C vs. SPI) medidos al arrancar; todo a `exp_NNN.csv` en la microSD. Procedimiento en `docs/experimentos.md` | `experimentos.cpp`, `estadisticas.cpp` |
| Modelos exportados | `modelo_cnn.h` (red 1D float32 + int8) y `modelo_bosque.h` (emlearn), generados por `analysis/entrenar_detector.py`. **Hoy entrenados con datos sintéticos**: solo para medir latencia | `modelo_*.h` |

**Reparto en los dos núcleos:** núcleo 1 (APP_CPU) = adquisición (prioridad 20) y procesamiento (10).
Núcleo 0 (PRO_CPU) = Wi-Fi y página web (el Wi-Fi de ESP-IDF corre en el núcleo 0), GPS, I2C (maniobras y ambiente),
microSD, estadísticas y LED. El `loop()` de Arduino se elimina para que el núcleo 1 quede libre y se pueda medir su ocio.

**Qué se comparte entre núcleos y cómo:** bloques del ADXL345 por el ping-pong (semáforos + cola); estado del GPS, I2C y
del nodo con un mutex cada uno; la señal de la gráfica y los umbrales con un spinlock (`portMUX`), porque la sección crítica
es de microsegundos y el núcleo 1 no debe esperar un mutex; la microSD con `mutexSD` (registro y página web).

### Detector por umbrales (parámetros por defecto)

| Parámetro | Valor | Rango en la página | Significado |
|---|---|---|---|
| `UMBRAL_V_MIN_KMH` | 5 km/h | 0–60 | Por debajo no se detecta |
| `UMBRAL_K_REL` | 6 | 2–20 | El cambio de aceleración debe superar 6 × la vibración de fondo (RMS) |
| `UMBRAL_P2P_MIN_G` | 0,30 g | 0,05–3 | Piso absoluto del cambio |
| `UMBRAL_REFRACTARIO_S` | 1 s | 0,2–10 | Separación mínima entre eventos |
| `UMBRAL_TAU_BASE_S` | 2 s | fijo | Memoria de la vibración de fondo (promedio exponencial de a²) |
| `UMBRAL_VENTANA_P2P_S` | 0,05 s | fijo | Ventana del cambio pico a pico |

Son valores de partida, **no calibrados**: se ajustan con los primeros recorridos etiquetados (el script de entrenamiento
compara el detector con las etiquetas y reporta su precisión y recall). Lo que se cambia en la página queda en la flash
(NVS, espacio `viaviva`) y sobrevive a los reinicios; **"Valores de fábrica"** vuelve a los de `config.h`. Cada cambio y los
valores con que arranca cada sesión quedan en `exp_NNN.csv` (filas `AJU`), para saber con qué umbrales se detectó.
El cambio se aplica entre dos bloques (cada 155 ms) sin borrar la línea base del detector.

### Página web del nodo

1. Encender el nodo. Crea la red Wi-Fi `VIA-VIVA-NODO` (nombre y clave en `include/secretos.h`; copiar de
   `include/secretos.example.h`. Si no existe, usa la clave de ejemplo y lo avisa por el monitor serie).
2. Conectar el celular a esa red y abrir **http://192.168.4.1**.
3. El copiloto oprime **Hueco / Resalto / Otro** al pasar por cada evento. La hora queda en `etiquetas_NNN.csv`.
4. "Modo mesa" ignora la velocidad del GPS para probar el detector golpeando el nodo sobre una mesa.
5. **Descargar los datos:** tarjeta "Archivos de la microSD" → **Ver archivos** → tocar el CSV. Se puede bajar el de la
   sesión en curso (llega hasta el último *flush*, ≤ 1 s de atraso). Mientras descarga, la página deja de actualizarse,
   pero el nodo sigue guardando.

| Ruta | Qué hace |
|---|---|
| `GET /` | La página (estado cada 1 s, gráfica cada 0,5 s) |
| `GET /estado` | JSON: sensores, último evento, velocidad, ambiente, microSD (sesión, remontajes, fallos, bloques perdidos), GPS (bytes, reinicios de la UART, segundos sin datos, HDOP) y causa del último reinicio |
| `GET /senal?desde=N` | JSON `{"fs":20,"n":total,"mg":[...]}`: puntos de \|a\| − 1 g en miligramos con número de orden > N (máx. 200 = 10 s). De cada 10 muestras se guarda la de mayor magnitud, para que un golpe corto no desaparezca |
| `GET /ajustes` | JSON con valor actual, por defecto, mínimo y máximo de `k`, `p2p`, `vmin`, `refr` |
| `POST /ajustes?k=6&p2p=0.3&vmin=5&refr=1` | Valida los rangos, guarda en la flash y aplica (400 con el motivo si algo está fuera). `?restaurar=1` = valores de fábrica |
| `GET /archivos` | JSON `[{"f":"crudo_012.csv","b":bytes}, ...]` con los CSV de la raíz de la tarjeta |
| `GET /descargar?f=crudo_012.csv` | Descarga por partes de 2 KB; solo nombres simples `.csv` (sin `/` ni `..`) |
| `POST /etiqueta?tipo=hueco` | Etiqueta `hueco`, `resalto` u `otro` |
| `POST /mesa?activo=1` | Modo mesa |

### Códigos del LED (GPIO 33)

Lo maneja solo `tareaLED` (`src/led_estado.cpp`). Se muestra **el problema más grave**.

| LED | Significado | Qué hacer |
|---|---|---|
| Encendido fijo | Arrancando (setup y experimentos E2–E4, unos segundos) | Esperar. Si no cambia en ~30 s, el arranque se colgó: ver el monitor serie |
| Parpadeo lento (0,5 s / 0,5 s) | Todo bien: llegan muestras, la microSD guarda y el GPS tiene fijación | — |
| 1 destello corto y pausa | Sin fijación GPS | Normal bajo techo y los primeros 1–5 min; salir a cielo abierto |
| 2 destellos cortos y pausa | GPS sin datos: no llegan bytes NMEA (la UART se reinicia cada 5 s) | Revisar TX del GPS → GPIO 16, alimentación y GND del GPS |
| 3 destellos cortos y pausa | microSD sin montar o fallando: **no se está guardando** | Revisar la tarjeta (FAT32, bien metida); se reintenta sola cada 10 s |
| 4 destellos cortos y pausa | ADXL345 no responde o llegan < 150 muestras/s | Revisar cables SPI del ADXL345 (CS 4, INT1 34); reiniciar |
| Parpadeo rápido durante 1 s | Aviso: evento detectado o etiqueta guardada | — |

### Robustez

- **Watchdog de tareas** (`esp_task_wdt`, 10 s, con reinicio): `tareaAdquisicion`, `tareaProcesamiento`, `tareaGPS`,
  `tareaI2C` (después de iniciar los sensores) y `tareaRegistro`. La web, las estadísticas y el LED no (una descarga larga
  ocupa la tarea web y no es una falla). Tras un reinicio empieza una sesión nueva; la causa (`esp_reset_reason`) queda en
  `exp_NNN.csv` (fila `ARR`) y en la página ("último reinicio: watchdog / bajo voltaje / ...").
- **GPS:** si no llega ningún byte en 5 s, se reinicia la UART2 y se cuenta. Si la fijación no se actualiza en 5 s
  (túnel, antena tapada), el GPS pasa a no válido y la **velocidad a 0**: sin GPS el detector no dispara (salvo modo mesa),
  en vez de seguir con una velocidad vieja.
- **microSD:** número de sesión con un contador en la flash (NVS) que además salta los números que ya tengan archivos en
  la tarjeta. Si no monta al arrancar, se reintenta cada 10 s. Si una escritura falla, se cierran los archivos, se
  desmonta y se vuelve a montar; la sesión sigue en los mismos archivos (se agrega al final, sin repetir encabezado).
  La librería SD abría como máximo 5 archivos y la sesión usa 6: ahora son 8 (`SD_MAX_ARCHIVOS`), así que antes
  `exp_NNN.csv` no se podía crear.
- **Corte de energía:** los archivos se fuerzan a la tarjeta cada 1 s. Se pierde como máximo **~1 s** de datos más lo que
  esté en las colas (normalmente < 0,2 s; en el peor caso 16 bloques del crudo = 2,5 s si la tarjeta o una descarga
  estaban demorando). Un corte justo mientras se escribe la FAT puede dañar el último archivo: pasarle `chkdsk` a la
  tarjeta en el PC antes de copiar.
- **Bloques del crudo perdidos:** si la cola del crudo se llena, el bloque se descarta y se cuenta (página web).

## Compilar y subir

```powershell
cd firmware\nodo-sensores
pio run                       # modo normal (FIFO + DMA)
pio run -e e1_polling         # E1: polling cada 5 ms
pio run -e e1_int_muestra     # E1: una interrupción por muestra
pio run -t upload
pio device monitor
```

Si `pio` no se reconoce, usar `%USERPROFILE%\.platformio\penv\Scripts\pio.exe` o la extensión PlatformIO de VS Code.
Si Windows bloquea `pio.exe` ("Una directiva de Control de aplicaciones bloqueó este archivo"), funciona igual con
`%USERPROFILE%\.platformio\penv\Scripts\python.exe -m platformio run`.

## Estado (5-nov-2026)

**Compilan** los tres entornos (`espressif32 @ 6.9.0`, tabla de particiones `min_spiffs.csv`). `esp32dev`: RAM estática
66 348 B (20,2 %), flash 944 269 B (48,0 % de 1,9 MB), con los experimentos, los modelos y la página nueva. La única
advertencia (`portUSING_MPU_WRAPPERS redefined`) viene del framework. El JavaScript de la página se revisó con Node
(sintaxis y una prueba con datos SIMULADOS); **nada se ha probado en hardware.**

### Solo se puede validar con la placa real `[VALIDAR EN PLACA]`

1. Arranque con la microSD puesta (los pines elegidos evitan 12 y 15, pero hay que confirmarlo) y que la flash sea de 4 MB.
2. ADXL345: `DEVID = 0xE5` y lectura de vuelta de la configuración. Algunos clones GY-291 fallan por SPI.
3. Que la interrupción de watermark llegue cada ~155 ms y que `overruns` sea 0 con microSD, GPS y **Wi-Fi** activos,
   también **mientras se descarga un CSV** y al guardar umbrales (escribir la flash detiene la caché unos ms).
4. Lecturas por DMA a 1,5 MHz (≤ 1,6 MHz no necesita pausa extra entre lecturas de la FIFO).
5. MPU-6050 (`WHO_AM_I = 0x68`) y VL53L0X en el mismo bus I2C a 400 kHz; signos de los ejes del giroscopio al girar.
6. GPS: 9600 baud de fábrica, 1 Hz de fábrica, retraso de la frase NMEA; que reiniciar la UART2 recupere un GPS sin datos.
7. microSD a 10 MHz por la matriz GPIO; que sacar y volver a meter la tarjeta produzca el remontaje (que la escritura
   falle de verdad y no quede guardada en el búfer); cuánto tarda `SD.begin` sin tarjeta.
8. Página web: que cargue en el celular, la gráfica se mueva, las etiquetas lleguen a la microSD mientras se adquiere y
   la **velocidad real de descarga** por el punto de acceso (cálculo: ~25 B por línea × 200 Hz ≈ 18 MB por hora de crudo).
9. Watchdog: que ninguna tarea lo dispare en operación normal (p. ej. el registro cuando la tarjeta demora).
10. Códigos del LED en cada caso (sin GPS, sin tarjeta, sin ADXL345).
11. Umbrales del detector y de las maniobras con recorridos reales.
12. Que el % de CPU estimado con el gancho de ocio sea coherente (la referencia se mide 1 s al arrancar).

### Decisiones y desvíos respecto al diseño

- **Watermark 31, no 32.** El campo `samples` de `FIFO_CTL` tiene 5 bits (máximo 31): interrupción cada 155 ms a 200 Hz.
- **microSD por la matriz GPIO** (14/27/13/32) porque los pines nativos de HSPI incluyen 12 y 15 (arranque).
- **Clasificación provisional por reglas** hasta tener el modelo entrenado; severidad y confianza también provisionales.
- **Eje vertical:** \|a\| − 1 g (no depende de la orientación). Pendiente: rotar al eje vertical con la gravedad en reposo.
- **Privacidad:** `crudo_*.csv` y `gps_*.csv` son datos de análisis (van a `data/raw/`); a la base final solo llegan eventos.
  La descarga por Wi-Fi solo funciona conectado a la red del nodo (con clave).
