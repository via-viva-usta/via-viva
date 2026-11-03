# firmware/

Código de los microcontroladores del nodo a bordo (PlatformIO, framework Arduino).

| Carpeta | Placa | Función |
|---|---|---|
| `nodo-sensores/` | ESP32 DevKit 30 pines (WROOM-32, `esp32dev`) | ADXL345 (SPI + FIFO + DMA), MPU-6050 y VL53L0X (I2C), GPS (UART), microSD, pulsador, detección de eventos, experimento E1 |
| `nodo-camara/` | ESP32-CAM AI-Thinker | Espera la orden por UART, toma la foto de evidencia y la difumina |

**Estado:** ambos proyectos compilan; **ninguno se ha probado en hardware**. Lo que solo se puede validar con la placa
real está en el README de cada proyecto y marcado en el código con `[VALIDAR EN PLACA]`.
