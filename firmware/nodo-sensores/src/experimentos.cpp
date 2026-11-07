// Experimentos E2, E3, E4 y memoria, medidos al arrancar: todavía no hay tareas propias corriendo, así que
// la medición no la perturban el Wi-Fi, la microSD ni la adquisición (el E1 sí se mide en operación).
#include "experimentos.h"

#include <Wire.h>

#include "esp_timer.h"
#include "estado.h"
#include "modelo_bosque.h"
#include "modelo_cnn.h"
#include "pines.h"

QueueHandle_t colaExp;

void registrarExp(const char* experimento, const char* condicion, const char* variable, float valor) {
    FilaExp f{};
    f.tMs = millis();
    strncpy(f.experimento, experimento, sizeof(f.experimento) - 1);
    strncpy(f.condicion, condicion, sizeof(f.condicion) - 1);
    strncpy(f.variable, variable, sizeof(f.variable) - 1);
    f.valor = valor;
    Serial.printf("EXP,%s,%s,%s,%.3f\n", f.experimento, f.condicion, f.variable, valor);
    if (colaExp) xQueueSend(colaExp, &f, 0);
}

const char* nombreModoAdq() {
    return MODO_ADQ == MODO_ADQ_POLLING ? "polling" : MODO_ADQ == MODO_ADQ_INT_MUESTRA ? "int_muestra" : "fifo_dma";
}

// ---- utilidades de medición ----
struct Medida {
    float primera = 0, media = 0, desv = 0, minimo = 1e9f, maximo = 0;
    int n = 0;
};

// Media y desviación estándar con el método de Welford (1962): una sola pasada, sin guardar las N muestras
// (memoria constante) y numéricamente estable. N ≥ 100 para reportar media ± desviación (R7).
template <typename F>
static Medida medir(F funcion, int repeticiones) {
    Medida m;
    double media = 0, m2 = 0;
    for (int i = 0; i < repeticiones; i++) {
        const int64_t t0 = esp_timer_get_time();
        funcion();
        const double us = (double)(esp_timer_get_time() - t0);
        if (i == 0) m.primera = (float)us;   // primera llamada: caché de flash todavía fría
        const double delta = us - media;
        media += delta / (i + 1);
        m2 += delta * (us - media);
        m.minimo = fminf(m.minimo, (float)us);
        m.maximo = fmaxf(m.maximo, (float)us);
    }
    m.n = repeticiones;
    m.media = (float)media;
    m.desv = repeticiones > 1 ? (float)sqrt(m2 / (repeticiones - 1)) : 0.0f;   // desviación muestral
    return m;
}

static void registrarMedida(const char* exp, const char* condicion, const char* prefijo, const Medida& m) {
    char v[24];
    snprintf(v, sizeof(v), "%s_primera_us", prefijo); registrarExp(exp, condicion, v, m.primera);
    snprintf(v, sizeof(v), "%s_media_us", prefijo);   registrarExp(exp, condicion, v, m.media);
    snprintf(v, sizeof(v), "%s_desv_us", prefijo);    registrarExp(exp, condicion, v, m.desv);
    snprintf(v, sizeof(v), "%s_n", prefijo);          registrarExp(exp, condicion, v, (float)m.n);
    snprintf(v, sizeof(v), "%s_min_us", prefijo);     registrarExp(exp, condicion, v, m.minimo);
    snprintf(v, sizeof(v), "%s_max_us", prefijo);     registrarExp(exp, condicion, v, m.maximo);
}

// Copias de los pesos float32 en SRAM (para E2). Sin "const": quedan en DRAM, no en flash.
static float w1Ram[sizeof(CNN_W1_F32) / 4], b1Ram[sizeof(CNN_B1_F32) / 4], w2Ram[sizeof(CNN_W2_F32) / 4],
    b2Ram[sizeof(CNN_B2_F32) / 4], w3Ram[sizeof(CNN_W3_F32) / 4], b3Ram[sizeof(CNN_B3_F32) / 4];
static int8_t qw1Ram[sizeof(CNN_W1_Q)], qw2Ram[sizeof(CNN_W2_Q)], qw3Ram[sizeof(CNN_W3_Q)];
static int32_t qb1Ram[sizeof(CNN_B1_Q) / 4], qb2Ram[sizeof(CNN_B2_Q) / 4], qb3Ram[sizeof(CNN_B3_Q) / 4];

static void experimentosModelo() {
    // Entrada fija y reproducible: un "golpe" sintético (la latencia no depende de los valores)
    static float x[CNN_ENTRADA];
    for (int i = 0; i < CNN_ENTRADA; i++) {
        const float t = (i - CNN_ENTRADA / 2) / 200.0f;
        x[i] = t >= 0 ? -0.8f * expf(-t / 0.08f) * cosf(2 * PI * 11 * t) : 0.02f * sinf(i);
    }
    memcpy(w1Ram, CNN_W1_F32, sizeof(w1Ram)); memcpy(b1Ram, CNN_B1_F32, sizeof(b1Ram));
    memcpy(w2Ram, CNN_W2_F32, sizeof(w2Ram)); memcpy(b2Ram, CNN_B2_F32, sizeof(b2Ram));
    memcpy(w3Ram, CNN_W3_F32, sizeof(w3Ram)); memcpy(b3Ram, CNN_B3_F32, sizeof(b3Ram));
    memcpy(qw1Ram, CNN_W1_Q, sizeof(qw1Ram)); memcpy(qb1Ram, CNN_B1_Q, sizeof(qb1Ram));
    memcpy(qw2Ram, CNN_W2_Q, sizeof(qw2Ram)); memcpy(qb2Ram, CNN_B2_Q, sizeof(qb2Ram));
    memcpy(qw3Ram, CNN_W3_Q, sizeof(qw3Ram)); memcpy(qb3Ram, CNN_B3_Q, sizeof(qb3Ram));
    const PesosCnnF32 f32Ram = {w1Ram, b1Ram, w2Ram, b2Ram, w3Ram, b3Ram};
    const PesosCnnQ qRam = {qw1Ram, qb1Ram, qw2Ram, qb2Ram, qw3Ram, qb3Ram};

    float salida[CNN_CLASES];
    volatile int clase = 0;   // volatile: que el compilador no elimine la inferencia
    const int N = 200;
    // E2: mismos pesos float32, en flash (const, vía caché) vs. copiados a SRAM
    registrarMedida("E2", "flash_f32", "cnn", medir([&] { clase = cnn_inferir_f32(x, CNN_PESOS_FLASH, salida); }, N));
    registrarMedida("E2", "sram_f32", "cnn", medir([&] { clase = cnn_inferir_f32(x, f32Ram, salida); }, N));
    // E3: float32 vs. int8 (los dos con pesos en SRAM y en flash)
    registrarMedida("E3", "f32_sram", "cnn", medir([&] { clase = cnn_inferir_f32(x, f32Ram, salida); }, N));
    registrarMedida("E3", "i8_sram", "cnn", medir([&] { clase = cnn_inferir_i8(x, qRam, salida); }, N));
    registrarMedida("E3", "i8_flash", "cnn", medir([&] { clase = cnn_inferir_i8(x, CNN_PESOS_Q, salida); }, N));
    // Bosque (emlearn): código con umbrales en línea (vive en flash)
    float caract[7] = {0.8f, 0.12f, 9.0f, 6.5f, 400.0f, -1.0f, 25.0f};
    registrarMedida("E3", "bosque_flash", "bosque", medir([&] { clase = bosque_predict(caract, 7); }, N));
    // Coincidencia float32 vs. int8 en la misma entrada (la del entrenamiento se reporta en Python)
    const int cf = cnn_inferir_f32(x, f32Ram, salida), ci = cnn_inferir_i8(x, qRam, salida);
    registrarExp("E3", "f32_vs_i8", "misma_clase", cf == ci ? 1 : 0);
    registrarExp("E3", "tamano", "cnn_f32_bytes", sizeof(CNN_W1_F32) + sizeof(CNN_B1_F32) + sizeof(CNN_W2_F32) +
                                                    sizeof(CNN_B2_F32) + sizeof(CNN_W3_F32) + sizeof(CNN_B3_F32));
    registrarExp("E3", "tamano", "cnn_i8_bytes", sizeof(CNN_W1_Q) + sizeof(CNN_B1_Q) + sizeof(CNN_W2_Q) +
                                                   sizeof(CNN_B2_Q) + sizeof(CNN_W3_Q) + sizeof(CNN_B3_Q));
    registrarExp("E3", "modelo", "sintetico", MODELO_SINTETICO);
    (void)clase;
}

static void experimentoBuses() {
    // E4: misma información útil por lectura (aceleración de 3 ejes) por cada bus
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 400000);
    Wire.beginTransmission(0x68);
    Wire.write(0x6B);
    Wire.write(0x01);
    const bool mpuOk = Wire.endTransmission() == 0;
    uint8_t b[14];
    const int N = 500;
    if (mpuOk) {
        const Medida i2c = medir([&] {
            Wire.beginTransmission(0x68);
            Wire.write(0x3B);
            Wire.endTransmission(false);
            Wire.requestFrom((uint8_t)0x68, (uint8_t)14);
            for (int i = 0; i < 14 && Wire.available(); i++) b[i] = Wire.read();
        }, N);
        registrarMedida("E4", "i2c_400k_14B", "lectura", i2c);
        registrarExp("E4", "i2c_400k_14B", "us_por_byte", i2c.media / 14);
        registrarExp("E4", "i2c_400k_14B", "cpu_pct_a_50Hz", i2c.media * 50 / 1e4f);
    } else {
        registrarExp("E4", "i2c_400k_14B", "mpu_no_responde", 1);
    }
    volatile int16_t z = 0;
    const Medida spi = medir([&] { z = adxl.leerMuestra().z; }, N);   // transacción por sondeo de 8 bytes (1 + 6 + relleno) a 1,5 MHz
    registrarMedida("E4", "spi_1M5_8B", "lectura", spi);
    registrarExp("E4", "spi_1M5_8B", "us_por_byte", spi.media / 8);   // 8 bytes por transacción desde el 7-nov (DMA alineado)
    registrarExp("E4", "spi_1M5_8B", "cpu_pct_a_200Hz", spi.media * 200 / 1e4f);
    (void)z;
}

static void experimentoMemoria() {
    registrarExp("MEM", "arranque", "heap_libre_B", ESP.getFreeHeap());
    registrarExp("MEM", "arranque", "heap_total_B", ESP.getHeapSize());
    registrarExp("MEM", "arranque", "programa_B", ESP.getSketchSize());
    registrarExp("MEM", "arranque", "flash_app_libre_B", ESP.getFreeSketchSpace());
    registrarExp("MEM", "arranque", "flash_chip_B", ESP.getFlashChipSize());
}

void experimentosArranque() {
    Serial.println("[EXP] Midiendo E2/E3 (modelo), E4 (buses) y memoria antes de arrancar las tareas...");
    experimentosModelo();
    experimentoBuses();
    experimentoMemoria();
}
