# firmware/nodo-sensores/pruebas

Un programa por sensor para la puesta en marcha (orden y errores típicos en `docs/montaje.md`).
Cada uno usa los pines de `../include/pines.h` y termina con `RESULTADO: PASA` o `RESULTADO: FALLA (...)` y una pista.

| Entorno | Archivo | Qué verifica |
|---|---|---|
| `i2c` | `prueba_i2c.cpp` | Escáner: MPU-6050 en 0x68 y VL53L0X en 0x29 |
| `adxl345` | `prueba_adxl345.cpp` | DEVID 0xE5, configuración, \|a\| ≈ 1 g en reposo, ruido, INT1 en GPIO 34 |
| `mpu6050` | `prueba_mpu6050.cpp` | WHO_AM_I, \|a\| ≈ 1 g, giro en reposo < 5 °/s, tiempo de lectura I2C; luego muestra el signo del giro |
| `vl53l0x` | `prueba_vl53l0x.cpp` | Inicio, 50 lecturas, timeouts y desviación |
| `gps` | `prueba_gps.cpp` | Bytes por UART2, frases NMEA válidas, fijación (al aire libre, hasta 5 min) |
| `microsd` | `prueba_microsd.cpp` | Montaje, tipo y tamaño, escritura de 256 KB, velocidad y relectura |
| `boton_led` | `prueba_boton_led.cpp` | LED (visual), pulsador en reposo y 3 pulsaciones con antirrebote |

```powershell
cd firmware\nodo-sensores\pruebas
pio run -e adxl345 -t upload
pio device monitor
```

**Estado (2-nov-2026):** los 7 programas **compilan**. No se han corrido en hardware.
