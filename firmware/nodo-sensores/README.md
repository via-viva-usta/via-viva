# firmware/nodo-sensores

Proyecto PlatformIO (framework Arduino sobre ESP-IDF) para la **ESP32-S3-DevKitC-1 N16R8** (16 MB flash, 8 MB PSRAM octal).
Pines en `include/pines.h` (copiados de la sección 5 de `CLAUDE.md`; son una **propuesta**).

## Qué hace

| Pieza | Cómo | Archivo |
|---|---|---|
| ADXL345 por SPI2 | Controlador propio a nivel de registros con el driver `spi_master` de ESP-IDF (DMA). FIFO en modo *stream* con watermark → INT1 (GPIO 14) → lote de lecturas por DMA → búfer **ping-pong** | `src/adxl345.*`, `tareaAdquisicion` |
| Ventana y evento | Búfer circular de 2 s, disparo por \|a\| − 1 g, características (pico, RMS, curtosis, factor de cresta, jerk) y **regla provisional** de clase | `include/bufer_circular.h`, `src/caracteristicas.h`, `tareaProcesamiento` |
| MPU-6050 y VL53L0X por I2C | MPU con controlador propio (14 bytes por lectura, se mide su duración para E4); VL53L0X con la librería de Pololu, modo continuo 20 ms | `src/mpu6050.h`, `tareaI2C` |
| GPS NEO-6M por UART1 | TinyGPSPlus; guarda la hora UTC de la fijación y el `esp_timer` de cuándo llegó, para interpolar en el ETL | `tareaGPS` |
| microSD por SPI3 | Archivos por sesión: `crudo_NNN.csv`, `eventos_NNN.csv`, `gps_NNN.csv`, `etiquetas_NNN.csv`, `fotos_NNN.csv` | `tareaRegistro` |
| Pulsador de etiquetado | Interrupción con antirrebote (250 ms) → `etiquetas_NNN.csv` | `isrPulsador` |
| Enlace con la cámara | UART2, protocolo `PING`/`FOTO,id,hora` → `OK`/`ERR` | `tareaCamara` |
| Experimento E1 | Cada 5 s imprime una línea `E1,...` con muestras recibidas vs. esperadas, desbordes de la FIFO, bloques perdidos, jitter, % de CPU por núcleo y µs por lectura I2C | `tareaEstadisticas` |

Reparto: **núcleo 1** = adquisición (prioridad 20) y procesamiento (10); **núcleo 0** = GPS, I2C, cámara, microSD y estadísticas.
El `loop()` de Arduino se elimina para que el núcleo 1 quede libre y se pueda medir su tiempo ocioso.

## Compilar y subir

```powershell
cd firmware\nodo-sensores
pio run                       # modo normal (FIFO + DMA)
pio run -e e1_polling         # E1: polling cada 5 ms
pio run -e e1_int_muestra     # E1: una interrupción por muestra
pio run -t upload             # cable en el puerto "UART" de la placa
pio device monitor
```

Si `pio` no se reconoce, usar `%USERPROFILE%\.platformio\penv\Scripts\pio.exe` o la extensión PlatformIO de VS Code.

## Estado (26-oct-2026)

**Compila** (PlatformIO, `espressif32 @ 6.9.0`) en los tres entornos, sin advertencias:

| Entorno | RAM estática | Flash |
|---|---|---|
| `esp32s3` (FIFO + DMA) | 26 496 B (8,1 %) | 397 081 B (6,1 %) |
| `e1_polling` | 26 488 B (8,1 %) | 396 261 B (6,0 %) |
| `e1_int_muestra` | 26 496 B (8,1 %) | 396 373 B (6,0 %) |

**Nada se ha probado en hardware.** No hay placa todavía.

### Solo se puede validar con la placa real `[VALIDAR EN PLACA]`

1. Que la placa sea de verdad N16R8: el arranque debe imprimir ~16 MB de flash y ~8 MB de PSRAM. Si la PSRAM sale en 0, la configuración `qio_opi` no coincide con el módulo.
2. ADXL345: `DEVID = 0xE5` y lectura de vuelta de `DATA_FORMAT`/`BW_RATE`. Algunos clones GY-291 fallan por SPI (diseño, sección 5).
3. Que la interrupción de watermark llegue cada ~155 ms y que `overruns` sea 0 con SD, GPS y cámara activos.
4. Que las lecturas por DMA a 1,5 MHz saquen bien la FIFO (hoja de datos: ≤ 1,6 MHz no necesita pausa extra entre lecturas).
5. MPU-6050 (`WHO_AM_I = 0x68`) y VL53L0X en el mismo bus I2C a 400 kHz; alcance del láser con sol fuerte.
6. GPS: velocidad en baudios (9600 de fábrica), tasa de fijaciones (1 Hz de fábrica; 5 Hz requiere configurarlo por UBX) y retraso de la frase NMEA.
7. microSD por SPI3 a 20 MHz (bajar a 4–10 MHz si falla `SD.begin`).
8. Enlace UART con la ESP32-CAM (niveles, cruce TX/RX, resistencias en serie).
9. Pulsador en GPIO 1 y LED en GPIO 2 (en algunas DevKitC-1 el LED RGB está en GPIO 38 o 48).
10. Que el % de CPU estimado con el gancho de ocio sea coherente (la referencia se mide 1 s al arrancar).

### Decisiones y desvíos respecto al diseño

- **Watermark 31, no 32.** El campo `samples` de `FIFO_CTL` tiene 5 bits (máximo 31). A 200 Hz da una interrupción cada
  155 ms y deja 1 muestra (5 ms) de margen antes del desborde; si aparecen `overruns`, bajarlo a 16–24 en `include/config.h`.
- **El DMA copia a un búfer interno y de ahí al ping-pong.** El ping-pong está entre la adquisición y el procesamiento:
  mientras se procesa una mitad, la otra se llena; si el procesamiento se atrasa se cuenta `bloques_perdidos`.
- **Clasificación provisional por reglas** (`clasificarProvisional`): no está validada; la reemplaza el modelo
  entrenado con los recorridos (analysis/). La severidad y la confianza también son provisionales.
- **Eje vertical:** por ahora se usa \|a\| − 1 g (no depende de la orientación). Pendiente: estimar la gravedad con el carro
  detenido y rotar al eje vertical (diseño, sección 5).
- **Hora del evento:** el nodo guarda la hora UTC de la última fijación y los ms transcurridos; la interpolación
  de hora y posición se hace en el ETL.
- **Privacidad:** `crudo_*.csv` y `gps_*.csv` son datos de análisis (van a `data/raw/`, ignorado por Git); a la base final
  solo llegan eventos.

### Pendiente

- Experimentos E2 (pesos en flash/SRAM/PSRAM) y E3 (float32 vs. int8, ESP-NN): requieren el modelo entrenado.
- Envío por Wi-Fi (store-and-forward) desde el núcleo 0.
- Simulación en Wokwi: Wokwi no tiene ADXL345; se podría simular el resto (MPU-6050, GPS, SD).
