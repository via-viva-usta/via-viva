// Estadísticas del experimento E1 (se reinician en cada reporte).
#pragma once
#include <Arduino.h>

struct EstadisticasE1 {
    uint32_t muestras = 0, overruns = 0, bloquesPerdidos = 0, timeouts = 0, interrupciones = 0;
    uint32_t nIntervalos = 0;
    double mediaIntervalo = 0, m2Intervalo = 0;   // Welford: media y varianza en línea
    int64_t minIntervalo = INT64_MAX, maxIntervalo = 0;
    int64_t usOcupado = 0;       // tiempo de pared dentro de la lectura (incluye espera del DMA)
    int64_t tInicio = 0;
};

extern EstadisticasE1 e1;
extern portMUX_TYPE muxE1;
extern volatile uint32_t contadorIdle[2];
extern uint32_t referenciaIdle[2];   // conteos/s sin carga, medidos al arrancar
