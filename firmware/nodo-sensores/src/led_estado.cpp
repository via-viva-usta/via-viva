// Núcleo 0: LED de estado (GPIO 33). Solo esta tarea mueve el LED. Muestra el problema MÁS GRAVE que haya;
// sirve para saber cómo va el nodo sin abrir la página web (tabla en README.md y docs/montaje.md).
//
//   Patrón                                 Significado
//   Encendido fijo                         Arrancando (setup y experimentos E2–E4, unos segundos). Si no cambia, se colgó
//   Parpadeo lento (0,5 s / 0,5 s)         Todo bien: llegan muestras, la microSD guarda y el GPS tiene fijación
//   1 destello corto y pausa               Sin fijación GPS (normal bajo techo y en los primeros minutos)
//   2 destellos cortos y pausa             GPS sin datos: no llegan bytes NMEA (cables TX/RX o alimentación)
//   3 destellos cortos y pausa             microSD sin montar o fallando: NO se está guardando nada
//   4 destellos cortos y pausa             ADXL345 no responde o llegan menos de 150 muestras/s
//   Parpadeo rápido durante 1 s            Aviso: se detectó un evento o se guardó una etiqueta
#include "estado.h"
#include "pines.h"

static constexpr uint32_t PASO_MS = 50;
static constexpr uint32_t DESTELLO_MS = 150, ENTRE_DESTELLOS_MS = 400, PAUSA_MS = 1200;

// Código del problema más grave (0 = ninguno)
static int codigoProblema(const EstadoNodo& n, bool gpsValido) {
    const uint32_t ahora = millis();
    const bool arrancado = ahora > 8000;   // los primeros segundos aún no hay muestras/s ni datos del GPS
    if (!n.adxlOk || (arrancado && n.muestrasPorSegundo < FS_HZ * 0.75f)) return 4;
    if (!n.sdOk) return 3;
    if (arrancado && (gpsBytes == 0 || ahora - gpsUltimoByteMs > GPS_SIN_DATOS_MS)) return 2;
    if (!gpsValido) return 1;
    return 0;
}

void tareaLED(void*) {
    uint32_t eventosAntes = 0, etiquetasAntes = 0;
    uint32_t avisoHasta = 0;
    for (;;) {
        const EstadoNodo n = copiarNodo();
        const uint32_t ahora = millis();
        if (n.eventos != eventosAntes || n.etiquetas != etiquetasAntes) {
            eventosAntes = n.eventos;
            etiquetasAntes = n.etiquetas;
            avisoHasta = ahora + 1000;
        }
        bool encendido;
        if ((int32_t)(avisoHasta - ahora) > 0) {
            encendido = (ahora / 100) % 2;                       // 5 Hz durante 1 s
        } else {
            const int codigo = codigoProblema(n, copiarGPS().valido);
            if (codigo == 0) {
                encendido = (ahora / 500) % 2;                   // latido de 1 Hz
            } else {
                const uint32_t ciclo = codigo * ENTRE_DESTELLOS_MS + PAUSA_MS;
                const uint32_t t = ahora % ciclo;
                encendido = t < codigo * ENTRE_DESTELLOS_MS && (t % ENTRE_DESTELLOS_MS) < DESTELLO_MS;
            }
        }
        digitalWrite(PIN_LED, encendido);
        vTaskDelay(pdMS_TO_TICKS(PASO_MS));
    }
}
