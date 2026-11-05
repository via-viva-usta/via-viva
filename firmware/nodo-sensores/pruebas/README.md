# firmware/nodo-sensores/pruebas

Un programa por sensor para la puesta en marcha (orden, conexiones y errores típicos en `docs/montaje.md`).
Cada uno usa los pines de `../include/pines.h` y termina con `RESULTADO: PASA` o `RESULTADO: FALLA (...)` y una pista.

| Entorno | Archivo | Qué verifica |
|---|---|---|
| `i2c` | `prueba_i2c.cpp` | Escáner: MPU-6050 en 0x68 y VL53L0X en 0x29; informa BH1750 (0x23) y BME280 (0x76/0x77) si hay |
| `adxl345` | `prueba_adxl345.cpp` | DEVID 0xE5, configuración, \|a\| ≈ 1 g en reposo, ruido, INT1 en GPIO 34 |
| `mpu6050` | `prueba_mpu6050.cpp` | WHO_AM_I, \|a\| ≈ 1 g, giro en reposo < 5 °/s, tiempo de lectura I2C; luego muestra el signo del giro |
| `vl53l0x` | `prueba_vl53l0x.cpp` | Inicio, 50 lecturas, timeouts y desviación |
| `gps` | `prueba_gps.cpp` | Bytes por UART2, frases NMEA válidas, fijación (al aire libre, hasta 5 min) |
| `microsd` | `prueba_microsd.cpp` | Montaje, tipo y tamaño, escritura de 256 KB, velocidad y relectura |
| `boton_led` | `prueba_boton_led.cpp` | LED (visual), pulsador en reposo y 3 pulsaciones con antirrebote |
| `dht22` | `prueba_dht22.cpp` | **Sensor de temperatura y humedad del nodo:** 10 lecturas en GPIO 25, ≥ 8 correctas, rangos y estabilidad |
| `bh1750` | `prueba_bh1750.cpp` | Responde en 0x23, lecturas válidas, tapar el sensor baja la luz |
| `bme280` | `prueba_bme280.cpp` | Solo si algún día se pone un BME280 (no se compró): autoprueba de la fórmula de Bosch (corre sin sensor), ID 0x60 (0x58 = BMP280 sin humedad), 10 lecturas |

```powershell
cd firmware\nodo-sensores\pruebas
pio run -e adxl345 -t upload
pio device monitor
```

Si Windows bloquea `pio.exe`, usar `%USERPROFILE%\.platformio\penv\Scripts\python.exe -m platformio` con los mismos argumentos.

**Estado (5-nov-2026):** los 10 programas **compilan**. No se han corrido en hardware.
Los de ambiente usan el mismo controlador del nodo (`../include/ambiente.h`). Para probar el LED con los códigos de estado
del firmware completo, ver la tabla "Códigos del LED" en `../README.md`.
