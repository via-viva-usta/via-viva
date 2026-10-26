// Características de una ventana de aceleración y clasificación PROVISIONAL.
// La clasificación por reglas es solo un marcador de posición: el modelo int8 entrenado
// con los recorridos (analysis/) la reemplaza en la semana del 3 al 6 de noviembre.
#pragma once
#include <math.h>
#include <stdint.h>

struct Caracteristicas {
    float pico;          // max |a_din| (g)
    float rms;           // raíz del promedio de a_din² (g)
    float curtosis;      // m4 / m2² (3 para ruido gaussiano; alto = impulsivo)
    float factorCresta;  // pico / rms
    float jerkMax;       // max |Δa| / Δt (g/s)
    float signoPico;     // -1 si el pico es una caída (hueco), +1 si es subida (resalto)
};

// a: aceleración dinámica (|a| - 1 g) de n muestras; fs en Hz
inline Caracteristicas calcularCaracteristicas(const float* a, int n, float fs) {
    Caracteristicas c{};
    if (n < 2) return c;
    double suma = 0;
    for (int i = 0; i < n; i++) suma += a[i];
    const double media = suma / n;
    double m2 = 0, m4 = 0;
    int iPico = 0;
    for (int i = 0; i < n; i++) {
        const double d = a[i] - media;
        m2 += d * d;
        m4 += d * d * d * d;
        if (fabsf(a[i]) > fabsf(a[iPico])) iPico = i;
        if (i > 0) {
            const float jerk = fabsf(a[i] - a[i - 1]) * fs;
            if (jerk > c.jerkMax) c.jerkMax = jerk;
        }
    }
    m2 /= n;
    m4 /= n;
    c.pico = fabsf(a[iPico]);
    c.signoPico = a[iPico] < 0 ? -1.0f : 1.0f;
    double cuad = 0;
    for (int i = 0; i < n; i++) cuad += (double)a[i] * a[i];
    c.rms = sqrtf((float)(cuad / n));
    c.curtosis = m2 > 1e-12 ? (float)(m4 / (m2 * m2)) : 0.0f;
    c.factorCresta = c.rms > 1e-6f ? c.pico / c.rms : 0.0f;
    return c;
}

enum class ClaseEvento : uint8_t { NORMAL = 0, HUECO, RESALTO, IMPACTO_FUERTE };

inline const char* nombreClase(ClaseEvento c) {
    switch (c) {
        case ClaseEvento::HUECO: return "hueco";
        case ClaseEvento::RESALTO: return "resalto";
        case ClaseEvento::IMPACTO_FUERTE: return "impacto_fuerte";
        default: return "normal";
    }
}

// Regla provisional (NO validada): se reemplaza por el clasificador entrenado.
inline ClaseEvento clasificarProvisional(const Caracteristicas& c, float umbralImpactoG) {
    if (c.pico >= umbralImpactoG) return ClaseEvento::IMPACTO_FUERTE;
    return c.signoPico < 0 ? ClaseEvento::HUECO : ClaseEvento::RESALTO;
}
