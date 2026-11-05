// Núcleo 0: GPS (UART2) e I2C (MPU-6050 + VL53L0X + maniobras a 50 Hz; ambiente cada PERIODO_AMBIENTE_MS).
// El ambiente va en la misma tarea porque comparte el bus I2C: así no hace falta un mutex del bus.
#include <TinyGPSPlus.h>
#include <VL53L0X.h>
#include <Wire.h>

#include "ambiente.h"
#include "esp_timer.h"
#include "estadisticas.h"
#include "estado.h"
#include "mpu6050.h"
#include "pines.h"

static TinyGPSPlus gps;
static MPU6050 mpu;
static VL53L0X tof;
static BME280 bme;
static BH1750 bh;
static DHT22 dht;

// Detecta qué sensores de ambiente hay. Temperatura y humedad: BME280 (o BMP280, sin humedad); si no hay, DHT22.
static void iniciarAmbiente(EstadoAmbiente& a) {
    if (bme.iniciar(Wire)) {
        strcpy(a.sensorTH, bme.tieneHumedad() ? "bme280" : "bmp280");
    } else {
        dht.iniciar(PIN_DHT22);
        float t, h;
        for (int intento = 0; intento < 3; intento++) {   // la primera lectura tras energizar suele fallar
            delay(2100);                                  // ≥ 2 s entre lecturas
            if (dht.leer(t, h) == DHT22::OK) {
                strcpy(a.sensorTH, "dht22");
                break;
            }
        }
    }
    a.luxOk = bh.iniciar(Wire, BH1750_DIR);
    Serial.printf("[AMBIENTE] temperatura/humedad: %s%s · BH1750: %s\n", a.sensorTH,
                  strcmp(a.sensorTH, "bmp280") == 0 ? " (es BMP280: NO mide humedad; usar DHT22)" : "",
                  a.luxOk ? "OK" : "NO RESPONDE");
}

static void leerAmbiente(EstadoAmbiente& a) {
    float t = NAN, h = NAN, p = NAN, lux = NAN;
    if (a.sensorTH[0] == 'b') {
        if (!bme.leer(t, h, p)) t = h = p = NAN;
    } else if (a.sensorTH[0] == 'd') {
        const DHT22::Error e = dht.leer(t, h);
        if (e != DHT22::OK) {
            t = h = NAN;
            Serial.printf("[AMBIENTE] DHT22: %s\n", DHT22::nombreError(e));
        }
    }
    if (a.luxOk && !bh.leer(lux)) lux = NAN;
    a.tempC = t;
    a.humPct = h;
    a.presHpa = p;
    a.lux = lux;
    a.tUs = esp_timer_get_time();
}

volatile uint32_t gpsBytes = 0, gpsReinicios = 0, gpsUltimoByteMs = 0;

// GPS robusto:
//   * Si no llega NINGÚN byte en GPS_SIN_DATOS_MS (el NEO-6M manda frases cada 1 s aunque no tenga fijación), se
//     reinicia la UART2 y se cuenta en gpsReinicios (lo muestra la página). Si sigue en cero: cables o alimentación.
//   * Si la fijación no se actualiza en GPS_FIX_VIEJO_MS (túnel, antena tapada, módulo desconectado), el GPS pasa a
//     no válido y la velocidad a 0: así el detector no sigue usando una velocidad vieja (sin GPS no detecta,
//     salvo en "modo mesa").
void tareaGPS(void*) {
    esp_task_wdt_add(nullptr);
    int64_t wdt = 0;
    float velAnterior = 0;
    int64_t tAnterior = 0;
    bool fixVigente = false;
    uint32_t ultimoReinicio = millis();
    for (;;) {
        avisarWdt(wdt);
        uint32_t n = 0;
        while (Serial2.available()) {
            gps.encode(Serial2.read());
            n++;
        }
        const uint32_t ahoraMs = millis();
        if (n) {
            gpsBytes += n;
            gpsUltimoByteMs = ahoraMs;
        } else if (ahoraMs - gpsUltimoByteMs > GPS_SIN_DATOS_MS && ahoraMs - ultimoReinicio > GPS_SIN_DATOS_MS) {
            // [VALIDAR EN PLACA] que reiniciar la UART recupere un GPS que dejó de enviar
            Serial2.end();
            Serial2.begin(GPS_BAUD, SERIAL_8N1, PIN_GPS_RX, PIN_GPS_TX);
            gpsReinicios++;
            ultimoReinicio = ahoraMs;
            Serial.printf("[GPS] sin datos en %lu s: UART2 reiniciada (%lu veces)\n",
                          (unsigned long)(GPS_SIN_DATOS_MS / 1000), (unsigned long)gpsReinicios);
        }
        if (fixVigente && esp_timer_get_time() - tAnterior > (int64_t)GPS_FIX_VIEJO_MS * 1000) {
            fixVigente = false;
            if (xSemaphoreTake(mutexGPS, pdMS_TO_TICKS(5)) == pdTRUE) {
                estadoGPS.valido = false;
                estadoGPS.velKmh = 0;
                xSemaphoreGive(mutexGPS);
            }
            Serial.println("[GPS] fijación perdida: velocidad 0 hasta la próxima");
        }
        if (gps.location.isUpdated()) {
            fixVigente = true;
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
            // Desaceleración entre fijaciones (para detectar frenadas con el GPS)
            const float dt = tAnterior ? (e.tFixUs - tAnterior) / 1e6f : 0;
            e.decelMs2 = (dt > 0.05f && dt < 3.0f) ? (velAnterior - e.velKmh) / 3.6f / dt : 0;
            velAnterior = e.velKmh;
            tAnterior = e.tFixUs;
            if (xSemaphoreTake(mutexGPS, pdMS_TO_TICKS(5)) == pdTRUE) {
                estadoGPS = e;
                xSemaphoreGive(mutexGPS);
            }
            xQueueSend(colaGpsSD, &e, 0);
        }
        vTaskDelay(pdMS_TO_TICKS(5));
    }
}

static float eje(const LecturaMPU& l, int indice, bool giro) {
    if (giro) return indice == 0 ? l.gx : indice == 1 ? l.gy : l.gz;
    return indice == 0 ? l.ax : indice == 1 ? l.ay : l.az;
}

void tareaI2C(void*) {
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 400000);
    const bool mpuOk = mpu.iniciar(Wire);
    tof.setTimeout(50);
    const bool tofOk = tof.init();
    if (tofOk) {
        tof.setMeasurementTimingBudget(20000);   // 20 ms por medida
        tof.startContinuous();
    }
    Serial.printf("[I2C] MPU-6050: %s · VL53L0X: %s\n", mpuOk ? "OK" : "NO RESPONDE", tofOk ? "OK" : "NO RESPONDE");
    EstadoAmbiente amb;
    iniciarAmbiente(amb);
    uint32_t ultimoAmbiente = millis() - PERIODO_AMBIENTE_MS;   // primera lectura de una vez

    DetectorManiobras maniobras;
    ParametrosManiobra pm;
    pm.giroMinDps = MANIOBRA_GIRO_MIN_DPS;
    pm.durGiroS = MANIOBRA_DUR_GIRO_S;
    pm.frenadaMinG = MANIOBRA_FRENADA_MIN_G;
    pm.durFrenadaS = MANIOBRA_DUR_FRENADA_S;
    pm.frenadaGpsMs2 = MANIOBRA_FRENADA_GPS_MS2;
    pm.vMinKmh = UMBRAL_V_MIN_KMH;
    maniobras.configurar(pm, 1000.0f / PERIODO_I2C_MS);
    uint32_t idManiobra = 0;

    // El watchdog se activa después de iniciar los sensores (el DHT22 puede tardar ~6 s en responder)
    esp_task_wdt_add(nullptr);
    int64_t wdt = 0;
    TickType_t ultimo = xTaskGetTickCount();
    for (;;) {
        avisarWdt(wdt);
        LecturaMPU l{};
        uint32_t us = 0;
        if (mpuOk) {
            const int64_t t0 = esp_timer_get_time();
            mpu.leerTodo(l);
            us = (uint32_t)(esp_timer_get_time() - t0);
            portENTER_CRITICAL(&muxE1);
            i2cSumaUs += us;
            i2cN++;
            if (us > i2cMaxUs) i2cMaxUs = us;
            portEXIT_CRITICAL(&muxE1);
        }
        uint16_t dist = 0;
        if (tofOk) {
            dist = tof.readRangeContinuousMillimeters();
            if (tof.timeoutOccurred()) dist = 0;
        }
        const EstadoGPS g = copiarGPS();
        if (millis() - ultimoAmbiente >= PERIODO_AMBIENTE_MS) {
            ultimoAmbiente = millis();
            leerAmbiente(amb);
            FilaAmbiente fa{amb, g};
            xQueueSend(colaAmbienteSD, &fa, 0);
        }
        const float giro = SIGNO_GIRO_MPU * eje(l, EJE_GIRO_MPU, true);
        const float aLong = SIGNO_LONG_MPU * eje(l, EJE_LONG_MPU, false);
        const Maniobra nueva = mpuOk ? maniobras.procesar(giro, aLong, g.velKmh, g.decelMs2) : Maniobra::NINGUNA;

        if (xSemaphoreTake(mutexI2C, pdMS_TO_TICKS(5)) == pdTRUE) {
            estadoI2C.mpuOk = mpuOk;
            estadoI2C.tofOk = tofOk;
            estadoI2C.giroVertDps = giro;
            estadoI2C.aLongG = aLong;
            estadoI2C.distanciaMm = dist;
            estadoI2C.usLecturaMpu = us;
            estadoI2C.maniobra = maniobras.activa();
            estadoI2C.amb = amb;
            xSemaphoreGive(mutexI2C);
        }
        if (nueva != Maniobra::NINGUNA) {   // cada maniobra queda como evento propio en la microSD
            Evento ev{};
            ev.id = 100000 + (++idManiobra);  // ids de maniobra separados de los de la vía
            ev.tUs = esp_timer_get_time();
            ev.clase = nueva == Maniobra::GIRO_IZQUIERDA ? ClaseEvento::GIRO_IZQUIERDA
                     : nueva == Maniobra::GIRO_DERECHA   ? ClaseEvento::GIRO_DERECHA
                                                         : ClaseEvento::FRENADA_BRUSCA;
            ev.maniobra = nueva;
            ev.gps = g;
            ev.msDesdeFix = g.tFixUs ? (int32_t)((ev.tUs - g.tFixUs) / 1000) : 0;
            xQueueSend(colaEventosSD, &ev, 0);
        }
        vTaskDelayUntil(&ultimo, pdMS_TO_TICKS(PERIODO_I2C_MS));
    }
}
