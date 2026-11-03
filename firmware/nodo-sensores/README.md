# firmware/nodo-sensores

Proyecto PlatformIO (framework Arduino sobre ESP-IDF) para la **ESP32 DevKit de 30 pines (WROOM-32, entorno `esp32dev`)**:
4 MB de flash, 520 KB de SRAM, sin PSRAM. Pines en `include/pines.h` (sección 5 de `CLAUDE.md`).

> **Cambio de placa (2-nov-2026):** antes era una ESP32-S3. Cambió: pines, buses (VSPI para el ADXL345, HSPI por la
> matriz GPIO para la microSD), UART2 para el GPS y UART1 para la cámara, sin PSRAM. E2 = flash vs. SRAM; E3 = float32 vs. int8.

## Qué hace

| Pieza | Cómo | Archivo |
|---|---|---|
| ADXL345 por VSPI | Controlador propio a nivel de registros con el driver `spi_master` de ESP-IDF (DMA). FIFO en modo *stream* con watermark 31 → INT1 (GPIO 34) → lote por DMA → búfer **ping-pong** | `adxl345.*`, `adquisicion.cpp` |
| **Detector por umbrales** (línea base del docente) | Evento si velocidad GPS > V_min **y** el cambio de aceleración vertical en 50 ms supera K × la vibración de fondo de esa calle (y un piso absoluto). Configurable en `include/config.h`; la misma regla en Python (`analysis/detector_umbral.py`) pre-etiqueta los recorridos | `detector_umbral.h`, `procesamiento.cpp` |
| **Maniobras** con el giroscopio del MPU-6050 | Giro a la izquierda / derecha (velocidad angular vertical) y frenada brusca (aceleración longitudinal o caída de velocidad GPS). Cada maniobra queda como evento propio, y un golpe que cae durante una maniobra se atribuye a ella y no a la vía (no se pide foto) | `maniobras.h`, `perifericos.cpp` |
| **Página web del nodo** (punto de acceso Wi-Fi) | Para el celular del copiloto: último evento, velocidad, estado de sensores y botones **Hueco / Resalto / Otro** que guardan la hora en la microSD. "Modo mesa" para probar sin carro | `servidor_web.cpp` |
| Ventana y características | Búfer circular de 2 s; pico, RMS, curtosis, factor de cresta, jerk; clase **provisional** por reglas hasta tener el modelo | `bufer_circular.h`, `caracteristicas.h` |
| MPU-6050 y VL53L0X por I2C | MPU con controlador propio (se mide su duración para E4); VL53L0X con la librería de Pololu | `mpu6050.h`, `perifericos.cpp` |
| GPS NEO-6M por UART2 | TinyGPSPlus; hora UTC de la fijación + `esp_timer` de llegada para interpolar en el ETL | `perifericos.cpp` |
| microSD por HSPI | Por sesión: `crudo_NNN.csv`, `eventos_NNN.csv`, `gps_NNN.csv`, `etiquetas_NNN.csv` (tipo y origen: web o botón), `fotos_NNN.csv` | `registro.cpp` |
| Enlace con la cámara | UART1, `PING` / `FOTO,id,hora` → `OK` / `ERR` | `perifericos.cpp` |
| Experimento E1 | Cada 5 s una línea `E1,...` por el monitor serie | `estadisticas.cpp` |

**Reparto en los dos núcleos:** núcleo 1 (APP_CPU) = adquisición (prioridad 20) y procesamiento (10).
Núcleo 0 (PRO_CPU) = Wi-Fi y página web (el Wi-Fi de ESP-IDF corre en el núcleo 0), GPS, I2C y maniobras, cámara,
microSD y estadísticas. El `loop()` de Arduino se elimina para que el núcleo 1 quede libre y se pueda medir su ocio.

### Detector por umbrales (parámetros por defecto)

| Parámetro | Valor | Significado |
|---|---|---|
| `UMBRAL_V_MIN_KMH` | 5 km/h | Por debajo no se detecta |
| `UMBRAL_K_REL` | 6 | El cambio de aceleración debe superar 6 × la vibración de fondo (RMS) |
| `UMBRAL_P2P_MIN_G` | 0,30 g | Piso absoluto del cambio |
| `UMBRAL_TAU_BASE_S` | 2 s | Memoria de la vibración de fondo (promedio exponencial de a²) |
| `UMBRAL_VENTANA_P2P_S` | 0,05 s | Ventana del cambio pico a pico |
| `UMBRAL_REFRACTARIO_S` | 1 s | Separación mínima entre eventos |

Son valores de partida, **no calibrados**: se ajustan con los primeros recorridos etiquetados (el script de entrenamiento
compara el detector con las etiquetas y reporta su precisión y recall).

### Página web del nodo

1. Encender el nodo. Crea la red Wi-Fi `VIA-VIVA-NODO` (nombre y clave en `include/secretos.h`; copiar de
   `include/secretos.example.h`. Si no existe, usa la clave de ejemplo y lo avisa por el monitor serie).
2. Conectar el celular a esa red y abrir **http://192.168.4.1**.
3. El copiloto oprime **Hueco / Resalto / Otro** al pasar por cada evento. La hora queda en `etiquetas_NNN.csv`.
4. "Modo mesa" ignora la velocidad del GPS para probar el detector golpeando el nodo sobre una mesa.

### Montaje del MPU-6050 (para las maniobras)

Eje **X hacia adelante** del carro y **Z hacia arriba**. Si se monta distinto, cambiar `EJE_GIRO_MPU`, `SIGNO_GIRO_MPU`,
`EJE_LONG_MPU` y `SIGNO_LONG_MPU` en `include/config.h` (ver `docs/montaje.md`).

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

## Estado (2-nov-2026)

**Compila** (`espressif32 @ 6.9.0`, `esp32dev`, tabla de particiones `min_spiffs.csv`): RAM estática 53 028 B (16,2 %),
flash 899 681 B (45,8 % de 1,9 MB). La única advertencia (`portUSING_MPU_WRAPPERS redefined`) viene del framework.
**Nada se ha probado en hardware.**

### Solo se puede validar con la placa real `[VALIDAR EN PLACA]`

1. Arranque con la microSD puesta (los pines elegidos evitan 12 y 15, pero hay que confirmarlo) y que la flash sea de 4 MB.
2. ADXL345: `DEVID = 0xE5` y lectura de vuelta de la configuración. Algunos clones GY-291 fallan por SPI.
3. Que la interrupción de watermark llegue cada ~155 ms y que `overruns` sea 0 con microSD, GPS, cámara y **Wi-Fi** activos.
4. Lecturas por DMA a 1,5 MHz (≤ 1,6 MHz no necesita pausa extra entre lecturas de la FIFO).
5. MPU-6050 (`WHO_AM_I = 0x68`) y VL53L0X en el mismo bus I2C a 400 kHz; signos de los ejes del giroscopio al girar.
6. GPS: 9600 baud de fábrica, 1 Hz de fábrica, retraso de la frase NMEA.
7. microSD a 10 MHz por la matriz GPIO.
8. Página web: que cargue en el celular y que las etiquetas lleguen a la microSD mientras se adquiere.
9. Umbrales del detector y de las maniobras con recorridos reales.
10. Que el % de CPU estimado con el gancho de ocio sea coherente (la referencia se mide 1 s al arrancar).

### Decisiones y desvíos respecto al diseño

- **Watermark 31, no 32.** El campo `samples` de `FIFO_CTL` tiene 5 bits (máximo 31): interrupción cada 155 ms a 200 Hz.
- **microSD por la matriz GPIO** (14/27/13/32) porque los pines nativos de HSPI incluyen 12 y 15 (arranque).
- **Clasificación provisional por reglas** hasta tener el modelo entrenado; severidad y confianza también provisionales.
- **Eje vertical:** \|a\| − 1 g (no depende de la orientación). Pendiente: rotar al eje vertical con la gravedad en reposo.
- **Privacidad:** `crudo_*.csv` y `gps_*.csv` son datos de análisis (van a `data/raw/`); a la base final solo llegan eventos.
