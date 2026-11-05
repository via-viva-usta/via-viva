// Señal en vivo para la gráfica de la página web: |a| - 1 g diezmada a SENAL_VIVO_HZ, en miligramos (int16).
// La escribe tareaProcesamiento (núcleo 1) y la lee la tarea web (núcleo 0). Un spinlock (portMUX) protege el
// búfer circular: la sección crítica más larga es copiar ≤ 200 enteros (decenas de µs), así que no frena la
// adquisición. Cada punto tiene un número de orden (1, 2, 3, ...) para que la página pida solo los nuevos.
#pragma once
#include <Arduino.h>

#include "bufer_circular.h"
#include "config.h"

class SenalVivo {
public:
    void agregar(int16_t mg) {
        portENTER_CRITICAL(&mux_);
        bufer_.agregar(mg);
        total_++;
        portEXIT_CRITICAL(&mux_);
    }

    // Copia los puntos con número de orden > desde (como máximo los que haya en el búfer) en destino.
    // Devuelve cuántos copió; total = número de orden del último punto. Si desde > total (el nodo se
    // reinició y la página tenía números viejos), copia todo el búfer.
    size_t copiarDesde(uint32_t desde, int16_t* destino, uint32_t& total) {
        portENTER_CRITICAL(&mux_);
        total = total_;
        const size_t hay = bufer_.cantidad();
        size_t nuevos = desde <= total_ ? (size_t)(total_ - desde) : hay;
        if (nuevos > hay) nuevos = hay;
        for (size_t j = 0; j < nuevos; j++) destino[j] = bufer_[hay - nuevos + j];
        portEXIT_CRITICAL(&mux_);
        return nuevos;
    }

private:
    BuferCircular<int16_t, SENAL_VIVO_PUNTOS> bufer_;
    uint32_t total_ = 0;
    portMUX_TYPE mux_ = portMUX_INITIALIZER_UNLOCKED;
};

extern SenalVivo senalVivo;   // definida en procesamiento.cpp
