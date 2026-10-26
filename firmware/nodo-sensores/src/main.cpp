// VÍA VIVA — nodo de sensores (ESP32-S3-DevKitC-1 N16R8)
//
// Reparto de tareas (FreeRTOS, doble núcleo):
//   Núcleo 1: tareaAdquisicion (ADXL345 por SPI + DMA) → búfer ping-pong → tareaProcesamiento
//   Núcleo 0: tareaGPS, tareaI2C (MPU-6050 + VL53L0X), tareaRegistro (microSD), tareaCamara, tareaEstadisticas
//
// Lo que solo se puede validar con la placa real está marcado con [VALIDAR EN PLACA].

#include <Arduino.h>
#include <SD.h>
#include <SPI.h>
#include <TinyGPSPlus.h>
#include <VL53L0X.h>
#include <Wire.h>

#include "adxl345.h"
#include "bufer_circular.h"
#include "caracteristicas.h"
#include "config.h"
#include "esp_freertos_hooks.h"
#include "esp_timer.h"
#include "mpu6050.h"
#include "pines.h"

// ============================================================================
// Tipos que viajan por las colas
// ============================================================================
struct Bloque {                  // una mitad del búfer ping-pong
    int64_t tUltimaUs;           // hora (esp_timer) de la muestra más reciente del bloque
    uint8_t n;
    MuestraAcc m[TAM_BLOQUE + 1];  // +1: la FIFO puede tener 33 datos (32 + registros de salida)
};

struct EstadoGPS {
    bool valido = false;
    double lat = 0, lon = 0;
    float velKmh = 0, hdop = 99;
    uint8_t satelites = 0;
    char utc[24] = "";           // hora UTC de la última fijación, ISO 8601
    int64_t tFixUs = 0;          // esp_timer cuando se completó esa fijación
};

struct EstadoI2C {
    bool mpuOk = false, tofOk = false;
    float gx = 0, gy = 0, gz = 0;
    uint16_t distanciaMm = 0;
    uint32_t usLecturaMpu = 0;   // E4: duración de una lectura I2C de 14 bytes
};

struct Evento {
    uint32_t id;
    int64_t tUs;
    ClaseEvento clase;
    float severidad, confianza;
    Caracteristicas c;
    EstadoGPS gps;               // copia de la última fijación
    int32_t msDesdeFix;          // para interpolar posición y hora en el ETL
    uint16_t distanciaMm;
};

struct RespuestaFoto {
    uint32_t idEvento;
    char texto[48];
};

// ============================================================================
// Estado global
// ============================================================================
static ADXL345 adxl;
static MPU6050 mpu;
static VL53L0X tof;
static TinyGPSPlus gps;
static SPIClass spiSD(HSPI);     // SPI3, separado del bus del acelerómetro

static EstadoGPS estadoGPS;
static EstadoI2C estadoI2C;
static SemaphoreHandle_t mutexGPS, mutexI2C;

// Búfer ping-pong: la adquisición llena una mitad mientras el procesamiento usa la otra.
static Bloque pingPong[2];
static SemaphoreHandle_t mitadLibre[2];
static Bloque bloqueDescarte;    // si ninguna mitad está libre, se drena la FIFO aquí (cuenta como pérdida)

static QueueHandle_t colaBloques;    // índice de la mitad llena (0/1)
static QueueHandle_t colaCrudo;      // Bloque → microSD
static QueueHandle_t colaEventosSD;  // Evento → microSD
static QueueHandle_t colaCamara;     // Evento → ESP32-CAM
static QueueHandle_t colaGpsSD;      // EstadoGPS → microSD
static QueueHandle_t colaEtiquetas;  // int64_t (esp_timer) del pulsador
static QueueHandle_t colaFotosSD;    // RespuestaFoto → microSD

static TaskHandle_t hAdquisicion;
static volatile int64_t tIsrUs = 0;
static bool sdOk = false;

// ---- Estadísticas del experimento E1 (se reinician en cada reporte) ----
struct EstadisticasE1 {
    uint32_t muestras = 0, overruns = 0, bloquesPerdidos = 0, timeouts = 0, interrupciones = 0;
    uint32_t nIntervalos = 0;
    double mediaIntervalo = 0, m2Intervalo = 0;   // Welford: media y varianza en línea
    int64_t minIntervalo = INT64_MAX, maxIntervalo = 0;
    int64_t usOcupado = 0;       // tiempo de pared dentro de la lectura (incluye espera del DMA)
    int64_t tInicio = 0;
};
static EstadisticasE1 e1;
static portMUX_TYPE muxE1 = portMUX_INITIALIZER_UNLOCKED;
static volatile uint32_t contadorIdle[2] = {0, 0};
static uint32_t referenciaIdle[2] = {1, 1};     // conteos/s sin carga, medidos al arrancar

// ============================================================================
// Interrupciones
// ============================================================================
static void IRAM_ATTR isrAdxl() {
    tIsrUs = esp_timer_get_time();
    BaseType_t despertar = pdFALSE;
    vTaskNotifyGiveFromISR(hAdquisicion, &despertar);
    portYIELD_FROM_ISR(despertar);
}

static void IRAM_ATTR isrPulsador() {
    static int64_t ultimo = 0;
    const int64_t t = esp_timer_get_time();
    if (t - ultimo < (int64_t)ANTIRREBOTE_MS * 1000) return;
    ultimo = t;
    BaseType_t despertar = pdFALSE;
    xQueueSendFromISR(colaEtiquetas, &t, &despertar);
    portYIELD_FROM_ISR(despertar);
}

// Se llama sin parar mientras el núcleo está ocioso: el conteo es proporcional al tiempo libre.
static bool idleCore0() { contadorIdle[0]++; return false; }
static bool idleCore1() { contadorIdle[1]++; return false; }

// ============================================================================
// Núcleo 1: adquisición
// ============================================================================
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

static void tareaAdquisicion(void*) {
    int idx = 0;
    xSemaphoreTake(mitadLibre[idx], portMAX_DELAY);
    Bloque* b = &pingPong[idx];
    b->n = 0;
    int64_t tAnterior = 0;
    TickType_t ultimoDespertar = xTaskGetTickCount();

    for (;;) {
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
        adxl.leerLoteDMA(b->m, n);
        b->n = n;
        b->tUltimaUs = tEvento;
        const int64_t t1 = esp_timer_get_time();
        portENTER_CRITICAL(&muxE1);
        e1.muestras += n;
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

// ============================================================================
// Núcleo 1: procesamiento (ventana → características → clasificación → evento)
// ============================================================================
static void tareaProcesamiento(void*) {
    static BuferCircular<float, VENTANA_MUESTRAS> ventana;   // aceleración dinámica (g)
    static float lineal[VENTANA_MUESTRAS];
    uint32_t idEvento = 0;
    int restantes = -1;                 // muestras que faltan tras el disparo (-1 = sin disparo)
    int64_t tDisparo = 0, tUltimoEvento = 0;

    for (;;) {
        int i;
        xQueueReceive(colaBloques, &i, portMAX_DELAY);
        const Bloque& b = pingPong[i];
        xQueueSend(colaCrudo, &b, 0);   // copia para el registro crudo (si la cola está llena se pierde)
        digitalWrite(PIN_LED, !digitalRead(PIN_LED));   // parpadeo = adquiriendo

        for (int k = 0; k < b.n; k++) {
            // Hora de cada muestra reconstruida desde la más reciente del bloque
            const int64_t tMuestra = b.tUltimaUs - (int64_t)(b.n - 1 - k) * PERIODO_US;
            const float ax = b.m[k].x * ADXL345::G_POR_LSB;
            const float ay = b.m[k].y * ADXL345::G_POR_LSB;
            const float az = b.m[k].z * ADXL345::G_POR_LSB;
            // Provisional: |a| - 1 g no depende de la orientación del nodo.
            // Pendiente: estimar la gravedad con el carro detenido y rotar al eje vertical.
            const float aDin = sqrtf(ax * ax + ay * ay + az * az) - 1.0f;
            ventana.agregar(aDin);

            if (restantes < 0 && fabsf(aDin) > UMBRAL_DISPARO_G &&
                tMuestra - tUltimoEvento > (int64_t)REFRACTARIO_MS * 1000) {
                restantes = POST_DISPARO;
                tDisparo = tMuestra;
            }
            if (restantes > 0) restantes--;
            if (restantes == 0 && ventana.lleno()) {
                restantes = -1;
                tUltimoEvento = tDisparo;
                for (size_t j = 0; j < ventana.cantidad(); j++) lineal[j] = ventana[j];

                Evento ev{};
                ev.id = ++idEvento;
                ev.tUs = tDisparo;
                ev.c = calcularCaracteristicas(lineal, ventana.cantidad(), FS_HZ);
                ev.clase = clasificarProvisional(ev.c, UMBRAL_IMPACTO_G);
                ev.severidad = fminf(1.0f, ev.c.pico / 4.0f);   // provisional
                ev.confianza = 0.0f;                             // sin modelo aún
                if (xSemaphoreTake(mutexGPS, pdMS_TO_TICKS(5)) == pdTRUE) {
                    ev.gps = estadoGPS;
                    xSemaphoreGive(mutexGPS);
                }
                ev.msDesdeFix = ev.gps.tFixUs ? (int32_t)((tDisparo - ev.gps.tFixUs) / 1000) : 0;
                if (xSemaphoreTake(mutexI2C, pdMS_TO_TICKS(5)) == pdTRUE) {
                    ev.distanciaMm = estadoI2C.distanciaMm;
                    xSemaphoreGive(mutexI2C);
                }
                xQueueSend(colaEventosSD, &ev, 0);
                xQueueSend(colaCamara, &ev, 0);
            } else if (restantes == 0) {
                restantes = -1;   // disparo antes de llenar la primera ventana: se descarta
            }
        }
        xSemaphoreGive(mitadLibre[i]);
    }
}

// ============================================================================
// Núcleo 0: GPS, I2C, cámara, microSD, estadísticas
// ============================================================================
static void tareaGPS(void*) {
    for (;;) {
        while (Serial1.available()) gps.encode(Serial1.read());
        if (gps.location.isUpdated()) {
            EstadoGPS e;
            e.valido = gps.location.isValid();
            e.lat = gps.location.lat();
            e.lon = gps.location.lng();
            e.velKmh = gps.speed.isValid() ? gps.speed.kmph() : 0;
            e.hdop = gps.hdop.isValid() ? gps.hdop.hdop() : 99;
            e.satelites = gps.satellites.isValid() ? gps.satellites.value() : 0;
            snprintf(e.utc, sizeof(e.utc), "%04d-%02d-%02dT%02d:%02d:%02d.%02dZ",
                     gps.date.year(), gps.date.month(), gps.date.day(),
                     gps.time.hour(), gps.time.minute(), gps.time.second(), gps.time.centisecond());
            // [VALIDAR EN PLACA] la frase NMEA llega ~decenas de ms después del instante de la fijación
            e.tFixUs = esp_timer_get_time();
            if (xSemaphoreTake(mutexGPS, pdMS_TO_TICKS(5)) == pdTRUE) {
                estadoGPS = e;
                xSemaphoreGive(mutexGPS);
            }
            xQueueSend(colaGpsSD, &e, 0);
        }
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}

static void tareaI2C(void*) {
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 400000);
    const bool mpuOk = mpu.iniciar(Wire);
    tof.setTimeout(50);
    const bool tofOk = tof.init();
    if (tofOk) {
        tof.setMeasurementTimingBudget(20000);   // 20 ms por medida
        tof.startContinuous();
    }
    Serial.printf("[I2C] MPU-6050: %s · VL53L0X: %s\n", mpuOk ? "OK" : "NO RESPONDE", tofOk ? "OK" : "NO RESPONDE");

    TickType_t ultimo = xTaskGetTickCount();
    for (;;) {
        LecturaMPU l{};
        uint32_t us = 0;
        if (mpuOk) {
            const int64_t t0 = esp_timer_get_time();
            mpu.leerTodo(l);
            us = (uint32_t)(esp_timer_get_time() - t0);
        }
        uint16_t dist = 0;
        if (tofOk) {
            dist = tof.readRangeContinuousMillimeters();
            if (tof.timeoutOccurred()) dist = 0;
        }
        if (xSemaphoreTake(mutexI2C, pdMS_TO_TICKS(5)) == pdTRUE) {
            estadoI2C.mpuOk = mpuOk;
            estadoI2C.tofOk = tofOk;
            estadoI2C.gx = l.gx; estadoI2C.gy = l.gy; estadoI2C.gz = l.gz;
            estadoI2C.distanciaMm = dist;
            estadoI2C.usLecturaMpu = us;
            xSemaphoreGive(mutexI2C);
        }
        vTaskDelayUntil(&ultimo, pdMS_TO_TICKS(PERIODO_I2C_MS));
    }
}

// Protocolo con la ESP32-CAM (docs/diagramas/01_arquitectura.md):
//   S3 → CAM: "FOTO,<id>,<utc_fix>+<ms>"   CAM → S3: "OK,<id>,<bytes>" o "ERR,<id>,<codigo>"
static void tareaCamara(void*) {
    Serial2.setTimeout(TIMEOUT_CAMARA_MS);
    Serial2.print("PING\n");
    const String pong = Serial2.readStringUntil('\n');
    Serial.printf("[CAM] PING → %s\n", pong.length() ? pong.c_str() : "(sin respuesta)");

    Evento ev;
    for (;;) {
        xQueueReceive(colaCamara, &ev, portMAX_DELAY);
        while (Serial2.available()) Serial2.read();   // descarta basura previa
        Serial2.printf("FOTO,%lu,%s+%ld\n", (unsigned long)ev.id, ev.gps.utc, (long)ev.msDesdeFix);
        String r = Serial2.readStringUntil('\n');
        r.trim();
        RespuestaFoto rf{};
        rf.idEvento = ev.id;
        snprintf(rf.texto, sizeof(rf.texto), "%s", r.length() ? r.c_str() : "TIMEOUT");
        xQueueSend(colaFotosSD, &rf, 0);
    }
}

static File abrirSiguiente(const char* prefijo, int sesion, const char* encabezado) {
    char ruta[32];
    snprintf(ruta, sizeof(ruta), "/%s_%03d.csv", prefijo, sesion);
    File f = SD.open(ruta, FILE_WRITE);
    if (f) f.println(encabezado);
    return f;
}

static void tareaRegistro(void*) {
    int sesion = 0;
    if (sdOk) {
        char ruta[32];
        do {
            snprintf(ruta, sizeof(ruta), "/crudo_%03d.csv", ++sesion);
        } while (SD.exists(ruta) && sesion < 999);
        Serial.printf("[SD] sesión %03d\n", sesion);
    }
    File fCrudo, fEventos, fGps, fEtiq, fFotos;
    if (sdOk) {
        // El registro crudo y el de GPS son para análisis (data/raw, no se publican).
        // A la base final solo llegan eventos.
        fCrudo = abrirSiguiente("crudo", sesion, "t_us,ax,ay,az");
        fEventos = abrirSiguiente("eventos", sesion,
            "id,t_us,clase,severidad,confianza,pico_g,rms_g,curtosis,factor_cresta,jerk_max_gps,"
            "gps_valido,lat,lon,vel_kmh,hdop,utc_fix,ms_desde_fix,distancia_mm");
        fGps = abrirSiguiente("gps", sesion, "t_us,utc,lat,lon,vel_kmh,hdop,satelites");
        fEtiq = abrirSiguiente("etiquetas", sesion, "t_us,utc_fix,ms_desde_fix");
        fFotos = abrirSiguiente("fotos", sesion, "id_evento,respuesta");
    }

    static Bloque b;
    Evento ev;
    EstadoGPS g;
    int64_t tEtiqueta;
    RespuestaFoto rf;
    uint32_t ultimoFlush = millis();
    char linea[200];

    for (;;) {
        while (xQueueReceive(colaCrudo, &b, 0) == pdTRUE) {
            for (int k = 0; sdOk && k < b.n; k++) {
                const int64_t t = b.tUltimaUs - (int64_t)(b.n - 1 - k) * PERIODO_US;
                const int len = snprintf(linea, sizeof(linea), "%lld,%d,%d,%d\n",
                                         (long long)t, b.m[k].x, b.m[k].y, b.m[k].z);
                fCrudo.write((const uint8_t*)linea, len);
            }
        }
        while (xQueueReceive(colaEventosSD, &ev, 0) == pdTRUE) {
            Serial.printf("[EVENTO] #%lu %s pico=%.2f g rms=%.3f g gps=%s\n", (unsigned long)ev.id,
                          nombreClase(ev.clase), ev.c.pico, ev.c.rms, ev.gps.valido ? "sí" : "no");
            if (sdOk) {
                fEventos.printf("%lu,%lld,%s,%.3f,%.3f,%.4f,%.4f,%.3f,%.3f,%.1f,%d,%.7f,%.7f,%.1f,%.1f,%s,%ld,%u\n",
                                (unsigned long)ev.id, (long long)ev.tUs, nombreClase(ev.clase), ev.severidad,
                                ev.confianza, ev.c.pico, ev.c.rms, ev.c.curtosis, ev.c.factorCresta, ev.c.jerkMax,
                                ev.gps.valido, ev.gps.lat, ev.gps.lon, ev.gps.velKmh, ev.gps.hdop, ev.gps.utc,
                                (long)ev.msDesdeFix, ev.distanciaMm);
            }
        }
        while (xQueueReceive(colaGpsSD, &g, 0) == pdTRUE) {
            if (sdOk) fGps.printf("%lld,%s,%.7f,%.7f,%.1f,%.1f,%u\n", (long long)g.tFixUs, g.utc, g.lat, g.lon,
                                  g.velKmh, g.hdop, g.satelites);
        }
        while (xQueueReceive(colaEtiquetas, &tEtiqueta, 0) == pdTRUE) {
            EstadoGPS copia;
            if (xSemaphoreTake(mutexGPS, pdMS_TO_TICKS(5)) == pdTRUE) {
                copia = estadoGPS;
                xSemaphoreGive(mutexGPS);
            }
            const long ms = copia.tFixUs ? (long)((tEtiqueta - copia.tFixUs) / 1000) : 0;
            Serial.printf("[ETIQUETA] t=%lld us\n", (long long)tEtiqueta);
            if (sdOk) fEtiq.printf("%lld,%s,%ld\n", (long long)tEtiqueta, copia.utc, ms);
        }
        while (xQueueReceive(colaFotosSD, &rf, 0) == pdTRUE) {
            Serial.printf("[CAM] evento #%lu → %s\n", (unsigned long)rf.idEvento, rf.texto);
            if (sdOk) fFotos.printf("%lu,%s\n", (unsigned long)rf.idEvento, rf.texto);
        }
        if (sdOk && millis() - ultimoFlush > 1000) {   // como máximo se pierde 1 s si se corta la energía
            fCrudo.flush(); fEventos.flush(); fGps.flush(); fEtiq.flush(); fFotos.flush();
            ultimoFlush = millis();
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

static void tareaEstadisticas(void*) {
    uint32_t idleAnt[2] = {contadorIdle[0], contadorIdle[1]};
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(PERIODO_ESTADISTICAS_MS));
        const int64_t ahora = esp_timer_get_time();
        EstadisticasE1 s;
        portENTER_CRITICAL(&muxE1);
        s = e1;
        e1 = EstadisticasE1();
        e1.tInicio = ahora;
        portEXIT_CRITICAL(&muxE1);

        const double seg = (ahora - s.tInicio) / 1e6;
        const double esperadas = seg * FS_HZ;
        const double jitter = s.nIntervalos > 1 ? sqrt(s.m2Intervalo / (s.nIntervalos - 1)) : 0;
        float cpu[2];
        for (int c = 0; c < 2; c++) {
            const uint32_t idle = contadorIdle[c] - idleAnt[c];
            idleAnt[c] = contadorIdle[c];
            cpu[c] = 100.0f * (1.0f - (float)(idle / seg) / referenciaIdle[c]);
        }
        EstadoI2C i2c;
        if (xSemaphoreTake(mutexI2C, pdMS_TO_TICKS(5)) == pdTRUE) {
            i2c = estadoI2C;
            xSemaphoreGive(mutexI2C);
        }
        // Línea CSV fácil de copiar del monitor serie para el informe de E1/E4
        Serial.printf("E1,modo=%d,seg=%.1f,muestras=%lu,esperadas=%.0f,overruns=%lu,bloques_perdidos=%lu,"
                      "timeouts=%lu,int=%lu,intervalo_us=%.1f,jitter_us=%.1f,min_us=%lld,max_us=%lld,"
                      "lectura_ocupada_pct=%.2f,cpu0_pct=%.1f,cpu1_pct=%.1f,i2c_mpu_us=%lu,heap=%u,psram=%u\n",
                      MODO_ADQ, seg, (unsigned long)s.muestras, esperadas, (unsigned long)s.overruns,
                      (unsigned long)s.bloquesPerdidos, (unsigned long)s.timeouts, (unsigned long)s.interrupciones,
                      s.mediaIntervalo, jitter, (long long)(s.nIntervalos ? s.minIntervalo : 0),
                      (long long)s.maxIntervalo, 100.0 * s.usOcupado / (seg * 1e6), cpu[0], cpu[1],
                      (unsigned long)i2c.usLecturaMpu, ESP.getFreeHeap(), ESP.getFreePsram());
    }
}

// ============================================================================
// Arranque
// ============================================================================
void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n=== VÍA VIVA · nodo de sensores ===");
    Serial.printf("Modo de adquisición (E1): %d · fs = %u Hz · watermark = %u\n", MODO_ADQ, FS_HZ, FIFO_WATERMARK);
    // [VALIDAR EN PLACA] Con N16R8 deben verse ~16 MB de flash y ~8 MB de PSRAM
    Serial.printf("Flash: %u B · PSRAM: %u B · heap libre: %u B\n", ESP.getFlashChipSize(), ESP.getPsramSize(),
                  ESP.getFreeHeap());

    pinMode(PIN_LED, OUTPUT);
    pinMode(PIN_PULSADOR, INPUT_PULLUP);
    pinMode(PIN_ADXL_INT1, INPUT);

    mutexGPS = xSemaphoreCreateMutex();
    mutexI2C = xSemaphoreCreateMutex();
    for (int i = 0; i < 2; i++) mitadLibre[i] = xSemaphoreCreateBinary(), xSemaphoreGive(mitadLibre[i]);
    colaBloques = xQueueCreate(2, sizeof(int));
    colaCrudo = xQueueCreate(8, sizeof(Bloque));
    colaEventosSD = xQueueCreate(8, sizeof(Evento));
    colaCamara = xQueueCreate(4, sizeof(Evento));
    colaGpsSD = xQueueCreate(8, sizeof(EstadoGPS));
    colaEtiquetas = xQueueCreate(8, sizeof(int64_t));
    colaFotosSD = xQueueCreate(4, sizeof(RespuestaFoto));

    // Referencia de ocio: 1 s sin tareas propias corriendo (para estimar % de CPU después)
    esp_register_freertos_idle_hook_for_cpu(idleCore0, 0);
    esp_register_freertos_idle_hook_for_cpu(idleCore1, 1);
    const uint32_t i0 = contadorIdle[0], i1 = contadorIdle[1];
    delay(1000);
    referenciaIdle[0] = max<uint32_t>(1, contadorIdle[0] - i0);
    referenciaIdle[1] = max<uint32_t>(1, contadorIdle[1] - i1);

    // ---- ADXL345 (SPI2 + DMA) ----
    // [VALIDAR EN PLACA] DEVID = 0xE5 y lectura de vuelta de la configuración
    const bool adxlOk = adxl.iniciar(PIN_ADXL_SCK, PIN_ADXL_MOSI, PIN_ADXL_MISO, PIN_ADXL_CS, SPI_ADXL_HZ);
    const bool cfgOk = adxlOk && adxl.configurar(FS_HZ, MODO_ADQ, FIFO_WATERMARK);
    Serial.printf("[ADXL345] DEVID=0x%02X (%s) · configuración %s\n", adxl.devid(),
                  adxlOk ? "OK" : "NO RESPONDE", cfgOk ? "OK" : "FALLÓ");

    // ---- microSD (SPI3) ----
    spiSD.begin(PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);
    sdOk = SD.begin(PIN_SD_CS, spiSD, SPI_SD_HZ);
    Serial.printf("[SD] %s\n", sdOk ? "OK" : "NO DETECTADA (se sigue sin registro)");

    // ---- UARTs ----
    Serial1.begin(GPS_BAUD, SERIAL_8N1, PIN_GPS_RX, PIN_GPS_TX);
    Serial2.begin(CAM_BAUD, SERIAL_8N1, PIN_CAM_RX, PIN_CAM_TX);

    // ---- Tareas ----
    e1.tInicio = esp_timer_get_time();
    xTaskCreatePinnedToCore(tareaAdquisicion, "adq", 4096, nullptr, 20, &hAdquisicion, 1);
    xTaskCreatePinnedToCore(tareaProcesamiento, "proc", 8192, nullptr, 10, nullptr, 1);
    xTaskCreatePinnedToCore(tareaGPS, "gps", 4096, nullptr, 8, nullptr, 0);
    xTaskCreatePinnedToCore(tareaI2C, "i2c", 4096, nullptr, 7, nullptr, 0);
    xTaskCreatePinnedToCore(tareaCamara, "cam", 4096, nullptr, 5, nullptr, 0);
    xTaskCreatePinnedToCore(tareaRegistro, "sd", 8192, nullptr, 4, nullptr, 0);
    xTaskCreatePinnedToCore(tareaEstadisticas, "stats", 4096, nullptr, 2, nullptr, 0);

    if (MODO_ADQ != MODO_ADQ_POLLING) attachInterrupt(PIN_ADXL_INT1, isrAdxl, RISING);
    attachInterrupt(PIN_PULSADOR, isrPulsador, FALLING);
}

void loop() {
    vTaskDelete(nullptr);   // todo corre en tareas; así el núcleo 1 queda libre para medir su ocio
}
