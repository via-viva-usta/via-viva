# firmware/

Código de los microcontroladores del nodo a bordo (PlatformIO, framework Arduino).

| Carpeta | Placa | Función |
|---|---|---|
| `nodo-sensores/` | ESP32 DevKit 30 pines (WROOM-32, `esp32dev`) | ADXL345 (SPI + FIFO + DMA), MPU-6050, VL53L0X, BME280 y BH1750 (I2C) o DHT22, GPS (UART), microSD, pulsador, detección de eventos, experimentos E1–E4 |

> **3-nov-2026:** la ESP32-CAM y el CP2102 salieron del diseño (la foto de evidencia la toma el **celular**: ver
> `docs/protocolo_fotos.md`). Su código quedó en `futuro/nodo-camara/` como trabajo futuro; ya no se compila ni se monta.

**Estado:** compila (3 entornos + 10 pruebas); **ninguno se ha probado en hardware**. Lo que solo se puede validar con la placa
real está en el README de cada proyecto y marcado en el código con `[VALIDAR EN PLACA]`.
