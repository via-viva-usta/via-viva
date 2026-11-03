// Experimentos de arquitectura E1–E4: filas que terminan en la microSD (exp_NNN.csv) y en el monitor serie.
//   E1  modo de adquisición (entorno de PlatformIO: esp32dev = FIFO+DMA, e1_polling, e1_int_muestra)
//   E2  pesos del modelo en flash vs. SRAM          (al arrancar)
//   E3  float32 vs. int8                            (al arrancar)
//   E4  lectura I2C (MPU-6050) vs. SPI (ADXL345)    (al arrancar y cada 5 s en operación)
//   MEM RAM y flash                                 (al arrancar)
#pragma once
#include <Arduino.h>

struct FilaExp {
    uint32_t tMs;
    char experimento[4];
    char condicion[20];
    char variable[24];
    float valor;
};

extern QueueHandle_t colaExp;
void registrarExp(const char* experimento, const char* condicion, const char* variable, float valor);
void experimentosArranque();          // E2, E3, E4 y memoria; se llama en setup() antes de crear las tareas
const char* nombreModoAdq();
