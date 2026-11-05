// Núcleo 1: procesamiento (ventana → detector por umbrales → características → clase → evento).
#include "bufer_circular.h"
#include "detector_umbral.h"
#include "estado.h"
#include "pines.h"

// La página web puede activar el "modo mesa": ignora la velocidad del GPS para probar el detector
// golpeando el nodo sobre una mesa, sin carro ni señal GPS.
volatile bool modoMesa = false;

static ClaseEvento claseDeManiobra(Maniobra m) {
    switch (m) {
        case Maniobra::GIRO_IZQUIERDA: return ClaseEvento::GIRO_IZQUIERDA;
        case Maniobra::GIRO_DERECHA: return ClaseEvento::GIRO_DERECHA;
        case Maniobra::FRENADA_BRUSCA: return ClaseEvento::FRENADA_BRUSCA;
        default: return ClaseEvento::NORMAL;
    }
}

void tareaProcesamiento(void*) {
    static BuferCircular<float, VENTANA_MUESTRAS> ventana;   // aceleración dinámica (g)
    static float lineal[VENTANA_MUESTRAS];
    DetectorUmbral detector;
    ParametrosUmbral p;
    p.vMinKmh = UMBRAL_V_MIN_KMH;
    p.kRel = UMBRAL_K_REL;
    p.p2pMinG = UMBRAL_P2P_MIN_G;
    p.tauBaseS = UMBRAL_TAU_BASE_S;
    p.ventanaP2PS = UMBRAL_VENTANA_P2P_S;
    p.refractarioS = UMBRAL_REFRACTARIO_S;
    detector.configurar(p, FS_HZ);

    uint32_t idEvento = 0;
    int restantes = -1;                 // muestras que faltan tras el disparo (-1 = sin disparo)
    int64_t tDisparo = 0;
    float razonDisparo = 0;
    uint32_t muestrasSeg = 0, crudoPerdido = 0;
    int64_t tSeg = esp_timer_get_time();

    for (;;) {
        int i;
        xQueueReceive(colaBloques, &i, portMAX_DELAY);
        const Bloque& b = pingPong[i];
        // Copia para el registro crudo (si la cola está llena se pierde y se cuenta)
        if (xQueueSend(colaCrudo, &b, 0) != pdTRUE) crudoPerdido++;
        digitalWrite(PIN_LED, !digitalRead(PIN_LED));   // parpadeo = adquiriendo
        const float velocidad = modoMesa ? 99.0f : copiarGPS().velKmh;

        for (int k = 0; k < b.n; k++) {
            // Hora de cada muestra reconstruida desde la más reciente del bloque
            const int64_t tMuestra = b.tUltimaUs - (int64_t)(b.n - 1 - k) * PERIODO_US;
            const float ax = b.m[k].x * ADXL345::G_POR_LSB;
            const float ay = b.m[k].y * ADXL345::G_POR_LSB;
            const float az = b.m[k].z * ADXL345::G_POR_LSB;
            // |a| - 1 g: no depende de la orientación del nodo (aproxima el cambio vertical).
            // Pendiente: estimar la gravedad con el carro detenido y rotar al eje vertical.
            const float aDin = sqrtf(ax * ax + ay * ay + az * az) - 1.0f;
            ventana.agregar(aDin);

            if (detector.procesar(aDin, velocidad) && restantes < 0) {
                restantes = POST_DISPARO;
                tDisparo = tMuestra;
                razonDisparo = detector.razonUltimoEvento();
            }
            if (restantes > 0) restantes--;
            if (restantes == 0) {
                restantes = -1;
                if (!ventana.lleno()) continue;   // disparo antes de llenar la primera ventana
                for (size_t j = 0; j < ventana.cantidad(); j++) lineal[j] = ventana[j];

                Evento ev{};
                ev.id = ++idEvento;
                ev.tUs = tDisparo;
                ev.razonUmbral = razonDisparo;
                ev.c = calcularCaracteristicas(lineal, ventana.cantidad(), FS_HZ);
                const EstadoI2C i2c = copiarI2C();
                ev.maniobra = i2c.maniobra;
                ev.distanciaMm = i2c.distanciaMm;
                // Durante una maniobra el golpe se atribuye a la maniobra, no a la vía.
                ev.clase = ev.maniobra != Maniobra::NINGUNA ? claseDeManiobra(ev.maniobra)
                                                            : clasificarProvisional(ev.c, UMBRAL_IMPACTO_G);
                ev.severidad = fminf(1.0f, ev.c.pico / 4.0f);   // provisional
                ev.confianza = 0.0f;                             // la pone el modelo cuando exista
                ev.gps = copiarGPS();
                ev.msDesdeFix = ev.gps.tFixUs ? (int32_t)((tDisparo - ev.gps.tFixUs) / 1000) : 0;
                xQueueSend(colaEventosSD, &ev, 0);
                if (xSemaphoreTake(mutexNodo, pdMS_TO_TICKS(5)) == pdTRUE) {
                    estadoNodo.ultimo = ev;
                    estadoNodo.hayUltimo = true;
                    estadoNodo.eventos++;
                    xSemaphoreGive(mutexNodo);
                }
            }
        }
        muestrasSeg += b.n;
        const int64_t ahora = esp_timer_get_time();
        if (ahora - tSeg >= 1000000) {
            if (xSemaphoreTake(mutexNodo, pdMS_TO_TICKS(5)) == pdTRUE) {
                estadoNodo.muestrasPorSegundo = muestrasSeg * 1e6f / (ahora - tSeg);
                estadoNodo.crudoPerdido = crudoPerdido;
                xSemaphoreGive(mutexNodo);
            }
            muestrasSeg = 0;
            tSeg = ahora;
        }
        xSemaphoreGive(mitadLibre[i]);
    }
}
