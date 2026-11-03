// Núcleo 0: cada 5 s imprime una línea "E1,..." con las estadísticas de adquisición.
#include "esp_timer.h"
#include "estadisticas.h"
#include "estado.h"
#include "experimentos.h"

void tareaEstadisticas(void*) {
    uint32_t idleAnt[2] = {contadorIdle[0], contadorIdle[1]};
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(PERIODO_ESTADISTICAS_MS));
        const int64_t ahora = esp_timer_get_time();
        EstadisticasE1 s;
        uint32_t sumaI2c, nI2c, maxI2c;
        portENTER_CRITICAL(&muxE1);
        s = e1;
        e1 = EstadisticasE1();
        e1.tInicio = ahora;
        sumaI2c = i2cSumaUs; nI2c = i2cN; maxI2c = i2cMaxUs;
        i2cSumaUs = i2cN = i2cMaxUs = 0;
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
        const EstadoI2C i2c = copiarI2C();
        // Línea CSV fácil de copiar del monitor serie para el informe de E1/E4
        Serial.printf("E1,modo=%d,seg=%.1f,muestras=%lu,esperadas=%.0f,overruns=%lu,bloques_perdidos=%lu,"
                      "timeouts=%lu,int=%lu,intervalo_us=%.1f,jitter_us=%.1f,min_us=%lld,max_us=%lld,"
                      "lectura_ocupada_pct=%.2f,cpu0_pct=%.1f,cpu1_pct=%.1f,i2c_mpu_us=%lu,heap=%u\n",
                      MODO_ADQ, seg, (unsigned long)s.muestras, esperadas, (unsigned long)s.overruns,
                      (unsigned long)s.bloquesPerdidos, (unsigned long)s.timeouts, (unsigned long)s.interrupciones,
                      s.mediaIntervalo, jitter, (long long)(s.nIntervalos ? s.minIntervalo : 0),
                      (long long)s.maxIntervalo, 100.0 * s.usOcupado / (seg * 1e6), cpu[0], cpu[1],
                      (unsigned long)i2c.usLecturaMpu, ESP.getFreeHeap());

        // Las mismas cifras, en filas, para exp_NNN.csv (las lee analysis/experimentos.py)
        const char* m = nombreModoAdq();
        registrarExp("E1", m, "segundos", seg);
        registrarExp("E1", m, "muestras", s.muestras);
        registrarExp("E1", m, "esperadas", esperadas);
        registrarExp("E1", m, "perdidas_pct", esperadas > 0 ? 100.0 * (esperadas - s.muestras) / esperadas : 0);
        registrarExp("E1", m, "overruns", s.overruns);
        registrarExp("E1", m, "bloques_perdidos", s.bloquesPerdidos);
        registrarExp("E1", m, "timeouts", s.timeouts);
        registrarExp("E1", m, "intervalo_us", s.mediaIntervalo);
        registrarExp("E1", m, "jitter_us", jitter);
        registrarExp("E1", m, "min_us", s.nIntervalos ? s.minIntervalo : 0);
        registrarExp("E1", m, "max_us", s.maxIntervalo);
        registrarExp("E1", m, "lectura_ocupada_pct", 100.0 * s.usOcupado / (seg * 1e6));
        registrarExp("E1", m, "cpu0_pct", cpu[0]);
        registrarExp("E1", m, "cpu1_pct", cpu[1]);
        registrarExp("E1", m, "heap_libre_B", ESP.getFreeHeap());
        if (nI2c) {
            registrarExp("E4", "operacion", "i2c_media_us", (float)sumaI2c / nI2c);
            registrarExp("E4", "operacion", "i2c_max_us", maxI2c);
        }
        if (s.muestras) registrarExp("E4", "operacion", "spi_us_por_muestra", (float)s.usOcupado / s.muestras);
    }
}
