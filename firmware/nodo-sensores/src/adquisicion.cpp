// Núcleo 1: adquisición del ADXL345 y estadísticas del experimento E1.
#include "esp_freertos_hooks.h"
#include "esp_timer.h"
#include "estadisticas.h"
#include "estado.h"

static volatile int64_t tIsrUs = 0;
static Bloque bloqueDescarte;    // si ninguna mitad está libre, se drena la FIFO aquí (cuenta como pérdida)

EstadisticasE1 e1;
portMUX_TYPE muxE1 = portMUX_INITIALIZER_UNLOCKED;
volatile uint32_t contadorIdle[2] = {0, 0};
uint32_t referenciaIdle[2] = {1, 1};
uint32_t i2cSumaUs = 0, i2cN = 0, i2cMaxUs = 0;

void IRAM_ATTR isrAdxl() {
    tIsrUs = esp_timer_get_time();
    BaseType_t despertar = pdFALSE;
    vTaskNotifyGiveFromISR(hAdquisicion, &despertar);
    portYIELD_FROM_ISR(despertar);
}

// Se llama sin parar mientras el núcleo está ocioso: el conteo es proporcional al tiempo libre.
static bool idleCore0() { contadorIdle[0]++; return false; }
static bool idleCore1() { contadorIdle[1]++; return false; }

void iniciarMedicionOcio() {
    esp_register_freertos_idle_hook_for_cpu(idleCore0, 0);
    esp_register_freertos_idle_hook_for_cpu(idleCore1, 1);
    const uint32_t i0 = contadorIdle[0], i1 = contadorIdle[1];
    delay(1000);
    referenciaIdle[0] = max<uint32_t>(1, contadorIdle[0] - i0);
    referenciaIdle[1] = max<uint32_t>(1, contadorIdle[1] - i1);
    e1.tInicio = esp_timer_get_time();
}

static void registrarIntervalo(int64_t intervalo) {
    portENTER_CRITICAL(&muxE1);
    e1.nIntervalos++;
    const double delta = intervalo - e1.mediaIntervalo;
    e1.mediaIntervalo += delta / e1.nIntervalos;
    e1.m2Intervalo += delta * (intervalo - e1.mediaIntervalo);
    if (intervalo < e1.minIntervalo) e1.minIntervalo = intervalo;
    if (intervalo > e1.maxIntervalo) e1.maxIntervalo = intervalo;
    portEXIT_CRITICAL(&muxE1);
}

// Entrega una mitad llena al procesamiento y toma la otra (si está libre).
static Bloque* entregarBloque(Bloque* actual, int& idx) {
    if (actual != &bloqueDescarte) {
        xQueueSend(colaBloques, &idx, 0);   // la cola tiene espacio para las dos mitades
        idx ^= 1;
    }
    if (xSemaphoreTake(mitadLibre[idx], 0) == pdTRUE) return &pingPong[idx];
    portENTER_CRITICAL(&muxE1);
    e1.bloquesPerdidos++;                   // el procesamiento va atrasado
    portEXIT_CRITICAL(&muxE1);
    return &bloqueDescarte;
}

void tareaAdquisicion(void*) {
    int idx = 0;
    xSemaphoreTake(mitadLibre[idx], portMAX_DELAY);
    Bloque* b = &pingPong[idx];
    b->n = 0;
    int64_t tAnterior = 0;
    [[maybe_unused]] TickType_t ultimoDespertar = xTaskGetTickCount();
    esp_task_wdt_add(nullptr);   // si la lectura del ADXL345 se cuelga 10 s, el nodo se reinicia
    int64_t wdt = 0;

    for (;;) {
        avisarWdt(wdt);
#if MODO_ADQ == MODO_ADQ_FIFO_DMA
        // Espera la interrupción de watermark. El tiempo de espera cubre el caso en que INT1
        // ya estaba en alto al arrancar (no hay flanco): se lee igual y se cuenta como timeout.
        const TickType_t espera = pdMS_TO_TICKS(2 * FIFO_WATERMARK * 1000 / FS_HZ);
        const bool hubo = ulTaskNotifyTake(pdTRUE, espera) > 0;
        const int64_t t0 = esp_timer_get_time();
        const int64_t tEvento = hubo ? tIsrUs : t0;
        const uint8_t fuente = adxl.fuenteInterrupcion();
        uint8_t n = adxl.muestrasEnFifo();
        if (n > TAM_BLOQUE + 1) n = TAM_BLOQUE + 1;
        const bool lecturaOk = adxl.leerLoteDMA(b->m, n);
        b->n = lecturaOk ? n : 0;  // no procesar datos viejos si el driver DMA falla
        b->tUltimaUs = tEvento;
        const int64_t t1 = esp_timer_get_time();
        portENTER_CRITICAL(&muxE1);
        if (lecturaOk) e1.muestras += n;
        else e1.bloquesPerdidos++;
        e1.usOcupado += t1 - t0;
        if (hubo) e1.interrupciones++; else e1.timeouts++;
        if (fuente & ADXL345::INT_OVERRUN) e1.overruns++;
        portEXIT_CRITICAL(&muxE1);
        // Intervalo por muestra entre interrupciones consecutivas (µs)
        if (hubo && tAnterior != 0 && n > 0) registrarIntervalo((tEvento - tAnterior) / n);
        if (hubo) tAnterior = tEvento;
        b = entregarBloque(b, idx);
        b->n = 0;
#else
#if MODO_ADQ == MODO_ADQ_INT_MUESTRA
        const bool hubo = ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(50)) > 0;
        const int64_t tEvento = hubo ? tIsrUs : esp_timer_get_time();
#else  // MODO_ADQ_POLLING: un tick de FreeRTOS es 1 ms, así que 5 ms se puede programar
        vTaskDelayUntil(&ultimoDespertar, pdMS_TO_TICKS(1000 / FS_HZ));
        const bool hubo = true;
        const int64_t tEvento = esp_timer_get_time();
#endif
        const int64_t t0 = esp_timer_get_time();
        b->m[b->n++] = adxl.leerMuestra();
        b->tUltimaUs = tEvento;
        const int64_t t1 = esp_timer_get_time();
        portENTER_CRITICAL(&muxE1);
        e1.muestras++;
        e1.usOcupado += t1 - t0;
        if (hubo) e1.interrupciones++; else e1.timeouts++;
        portEXIT_CRITICAL(&muxE1);
        if (tAnterior != 0) registrarIntervalo(tEvento - tAnterior);
        tAnterior = tEvento;
        if (b->n >= FIFO_WATERMARK) {
            b = entregarBloque(b, idx);
            b->n = 0;
        }
#endif
    }
}
