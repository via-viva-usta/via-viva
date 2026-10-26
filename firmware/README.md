# firmware/

Código de los microcontroladores del nodo a bordo (PlatformIO, framework Arduino).

| Carpeta | Placa | Función |
|---|---|---|
| `nodo-sensores/` | ESP32-S3-DevKitC-1 N16R8 | ADXL345 (SPI), MPU-6050 y VL53L0X (I2C), GPS (UART), microSD, pulsador, detección de eventos |
| `nodo-camara/` | ESP32-CAM AI-Thinker | Espera la orden por UART, toma la foto de evidencia y la difumina |

**Estado:** pendiente (Fase 2). Aún no hay hardware: lo que solo se puede validar con la placa real se marca en el README de cada proyecto.
