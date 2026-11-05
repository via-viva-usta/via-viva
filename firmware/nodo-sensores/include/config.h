// Parámetros de diseño de la señal (CLAUDE.md, sección 6) y del firmware.
#pragma once
#include <stdint.h>

// ---- Muestreo ----
// 200 Hz es la hipótesis de trabajo; se valida con el espectro de los primeros recorridos.
constexpr uint16_t FS_HZ = 200;
constexpr uint32_t PERIODO_US = 1000000UL / FS_HZ;

// ---- Experimento E1: modo de adquisición ----
#define MODO_ADQ_POLLING      0   // la tarea lee una muestra cada 5 ms (vTaskDelayUntil)
#define MODO_ADQ_INT_MUESTRA  1   // DATA_READY en INT1 → una interrupción por muestra
#define MODO_ADQ_FIFO_DMA     2   // watermark de la FIFO en INT1 → lote por DMA → búfer ping-pong
#ifndef MODO_ADQ
#define MODO_ADQ MODO_ADQ_FIFO_DMA
#endif

// ---- FIFO del ADXL345 ----
// El diseño pedía 32, pero el campo 'samples' de FIFO_CTL tiene 5 bits: el máximo es 31.
// A 200 Hz: interrupción cada 31 × 5 ms = 155 ms y queda 1 muestra (5 ms) de margen antes de
// desbordar la FIFO de 32. Si en la placa real aparecen desbordes, bajar a 16-24.
constexpr uint8_t FIFO_WATERMARK = 31;
constexpr uint8_t TAM_BLOQUE = 32;          // capacidad de cada mitad del búfer ping-pong

// ---- SPI del ADXL345 ----
// Hasta 1,6 MHz el byte de dirección ya da los 5 µs que la FIFO necesita entre lecturas
// (hoja de datos ADXL345). Por encima habría que agregar retardo entre transacciones.
constexpr int SPI_ADXL_HZ = 1500000;
// La microSD va por la matriz GPIO (máx. ~26 MHz); 10 MHz deja margen con cables largos
constexpr int SPI_SD_HZ = 10000000;

// ---- Ventana y detección ----
constexpr uint16_t VENTANA_MUESTRAS = 400;   // 2 s a 200 Hz (2,4 KB con 3 ejes int16)
constexpr uint16_t POST_DISPARO = 100;       // muestras que se esperan después del disparo (0,5 s)
constexpr float UMBRAL_IMPACTO_G = 2.0f;     // clasificación provisional: pico mayor → impacto fuerte

// Detector por umbrales (src/detector_umbral.h; mismos valores por defecto que analysis/detector_umbral.py)
constexpr float UMBRAL_V_MIN_KMH = 5.0f;
constexpr float UMBRAL_K_REL = 6.0f;
constexpr float UMBRAL_P2P_MIN_G = 0.30f;
constexpr float UMBRAL_TAU_BASE_S = 2.0f;
constexpr float UMBRAL_VENTANA_P2P_S = 0.05f;
constexpr float UMBRAL_REFRACTARIO_S = 1.0f;

// ---- Maniobras (src/maniobras.h) ----
// Montaje del MPU-6050 (docs/montaje.md): X hacia adelante del carro, Z hacia arriba.
// Si se monta distinto, cambiar el eje (0 = X, 1 = Y, 2 = Z) y el signo.
constexpr int EJE_GIRO_MPU = 2;              // giro alrededor del eje vertical
constexpr float SIGNO_GIRO_MPU = 1.0f;       // +1: positivo = antihorario visto desde arriba = izquierda
constexpr int EJE_LONG_MPU = 0;              // aceleración hacia adelante
constexpr float SIGNO_LONG_MPU = 1.0f;
constexpr float MANIOBRA_GIRO_MIN_DPS = 15.0f;
constexpr float MANIOBRA_DUR_GIRO_S = 1.0f;
constexpr float MANIOBRA_FRENADA_MIN_G = 0.30f;
constexpr float MANIOBRA_DUR_FRENADA_S = 0.5f;
constexpr float MANIOBRA_FRENADA_GPS_MS2 = 2.5f;

// ---- Punto de acceso Wi-Fi y página web (src/servidor_web.cpp) ----
// El nombre y la clave vienen de include/secretos.h (ignorado por Git); si no existe se usa secretos.example.h.
constexpr uint8_t AP_CANAL = 6;
constexpr uint8_t AP_MAX_CLIENTES = 2;

// ---- microSD (src/registro.cpp) ----
// Archivos abiertos a la vez: los 6 de la sesión + 1 para descargar por Wi-Fi + 1 para listar.
// (La librería SD trae 5 por defecto: el 6.º archivo de la sesión, exp_NNN.csv, no se podía abrir.)
constexpr uint8_t SD_MAX_ARCHIVOS = 8;
constexpr uint32_t SD_FLUSH_MS = 1000;       // cada cuánto se fuerzan los datos a la tarjeta
constexpr uint32_t SD_REINTENTO_MS = 10000;  // si la tarjeta no monta, se reintenta cada 10 s

// ---- Robustez ----
constexpr uint32_t WDT_TAREAS_S = 10;        // watchdog de tareas: si una tarea crítica no avisa en 10 s, se reinicia
constexpr uint32_t GPS_SIN_DATOS_MS = 5000;  // sin bytes NMEA en 5 s (el NEO-6M manda cada 1 s) → reiniciar UART2
constexpr uint32_t GPS_FIX_VIEJO_MS = 5000;  // fijación sin actualizar en 5 s → GPS no válido y velocidad 0

// ---- Otros ----
constexpr uint32_t GPS_BAUD = 9600;
constexpr uint32_t PERIODO_I2C_MS = 20;      // MPU-6050 + VL53L0X a 50 Hz
constexpr uint32_t ANTIRREBOTE_MS = 250;
constexpr uint32_t PERIODO_ESTADISTICAS_MS = 5000;

// ---- Ambiente (include/ambiente.h): BME280 o DHT22 + BH1750 ----
// Se registra en ambiente_NNN.csv con la hora GPS. 10 s basta: temperatura, humedad y luz cambian lento,
// y el DHT22 no admite lecturas a menos de 2 s.
constexpr uint32_t PERIODO_AMBIENTE_MS = 10000;
constexpr uint8_t BH1750_DIR = 0x23;         // ADDR a GND (0x5C si ADDR en alto)
