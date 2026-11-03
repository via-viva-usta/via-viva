// Pines del nodo de sensores — ESP32 DevKit de 30 pines (WROOM-32, entorno esp32dev).
// Fuente: CLAUDE.md, sección 5. Verificar contra la placa real antes de soldar.
//
// Prohibidos o limitados: 0, 2, 5, 12, 15 (arranque) · 6-11 (flash interna) · 1 y 3 (UART0, monitor)
// · 34-39 solo entradas y SIN pull-up interno.
#pragma once

// ADXL345 por VSPI (SPI3_HOST), con el driver spi_master de ESP-IDF y DMA.
// SCK/MISO/MOSI en sus pines nativos de VSPI; el CS nativo (GPIO 5) es de arranque, por eso va en el 4.
#define PIN_ADXL_SCK   18
#define PIN_ADXL_MISO  19
#define PIN_ADXL_MOSI  23
#define PIN_ADXL_CS    4
#define PIN_ADXL_INT1  34   // solo entrada: sirve porque el INT1 del ADXL345 es push-pull

// microSD por HSPI (SPI2_HOST) enrutado por la matriz GPIO.
// Los pines nativos de HSPI (14/12/13/15) chocan con 12 y 15, que son de arranque.
#define PIN_SD_SCK   14
#define PIN_SD_MISO  27
#define PIN_SD_MOSI  13
#define PIN_SD_CS    32

// I2C: MPU-6050 (0x68), VL53L0X (0x29), BME280 (0x76; 0x77 si SDO en alto) y BH1750 (0x23 con ADDR a GND)
#define PIN_I2C_SDA  21
#define PIN_I2C_SCL  22

// GPS NEO-6M por UART2: TX del GPS → GPIO 16 (RX del ESP32), RX del GPS ← GPIO 17 (TX del ESP32)
#define PIN_GPS_RX   16
#define PIN_GPS_TX   17

// DHT22: solo si no hay BME280 (plan B de temperatura y humedad). Un hilo bidireccional con pull-up de 10 kΩ:
// necesita un pin de entrada/salida (el 35 no sirve). El 25 quedó libre al retirar la ESP32-CAM (3-nov).
#define PIN_DHT22    25

#define PIN_PULSADOR 26     // a GND, con pull-up interno (los pines 34-39 no lo tienen)
#define PIN_LED      33
