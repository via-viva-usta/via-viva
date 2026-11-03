# firmware/nodo-sensores

Proyecto PlatformIO (framework Arduino sobre ESP-IDF) para la **ESP32 DevKit de 30 pines (WROOM-32, entorno `esp32dev`)**:
4 MB de flash, 520 KB de SRAM, sin PSRAM. Pines en `include/pines.h` (copiados de la sección 5 de `CLAUDE.md`).

> **Cambio de placa (2-nov-2026):** antes era una ESP32-S3. Cambió: pines, buses (VSPI para el ADXL345, HSPI por la
> matriz GPIO para la microSD), UART2 para el GPS y UART1 para la cámara, sin PSRAM. E2 = flash vs. SRAM; E3 = float32 vs. int8.

**Estado:** compila en los tres entornos (`esp32dev`, `e1_polling`, `e1_int_muestra`). **Nada se ha probado en hardware.**
La descripción completa está en la sección siguiente al terminar la tarea 2 (detector, maniobras y servidor web).
