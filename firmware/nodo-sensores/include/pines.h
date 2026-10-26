// Pines del nodo de sensores (CLAUDE.md, sección 5).
// PROPUESTA: verificar contra la placa real antes de soldar.
// Evitados: 0, 3, 45, 46 (arranque) · 19-20 (USB) · 26-32 (flash) · 35-37 (PSRAM octal) · 43-44 (UART0, monitor).
#pragma once

// ADXL345 por SPI2 (FSPI), manejado con el driver spi_master de ESP-IDF (con DMA)
#define PIN_ADXL_CS    10
#define PIN_ADXL_MOSI  11
#define PIN_ADXL_SCK   12
#define PIN_ADXL_MISO  13
#define PIN_ADXL_INT1  14   // watermark de la FIFO (o DATA_READY en el modo 1)

// microSD por SPI3 (HSPI en Arduino), bus separado del acelerómetro
#define PIN_SD_CS    4
#define PIN_SD_MOSI  5
#define PIN_SD_SCK   6
#define PIN_SD_MISO  7

// I2C: MPU-6050 (0x68) y VL53L0X (0x29)
#define PIN_I2C_SDA  8
#define PIN_I2C_SCL  9

// GPS NEO-6M por UART1: TX del GPS → GPIO 17 (RX del ESP), RX del GPS ← GPIO 18 (TX del ESP)
#define PIN_GPS_RX   17
#define PIN_GPS_TX   18

// Enlace con la ESP32-CAM por UART2: GPIO 15 = TX del S3, GPIO 16 = RX del S3
#define PIN_CAM_TX   15
#define PIN_CAM_RX   16

#define PIN_PULSADOR 1      // a GND, con pull-up interno
#define PIN_LED      2
