// Prueba del ADXL345 por VSPI (SCK 18, MISO 19, MOSI 23, CS 4) e INT1 en GPIO 34.
// Usa la librería SPI de Arduino (no el DMA del firmware): primero comprobar el cableado de la forma más simple.
// Dejar el módulo QUIETO y plano durante la prueba.
#include <SPI.h>

#include "pines.h"
#include "resultado.h"

static SPIClass vspi(VSPI);
static const SPISettings AJUSTES(1000000, MSBFIRST, SPI_MODE3);

uint8_t leer(uint8_t reg) {
    vspi.beginTransaction(AJUSTES);
    digitalWrite(PIN_ADXL_CS, LOW);
    vspi.transfer(reg | 0x80);
    const uint8_t v = vspi.transfer(0);
    digitalWrite(PIN_ADXL_CS, HIGH);
    vspi.endTransaction();
    return v;
}

void escribir(uint8_t reg, uint8_t v) {
    vspi.beginTransaction(AJUSTES);
    digitalWrite(PIN_ADXL_CS, LOW);
    vspi.transfer(reg & 0x3F);
    vspi.transfer(v);
    digitalWrite(PIN_ADXL_CS, HIGH);
    vspi.endTransaction();
}

void leerXYZ(float& x, float& y, float& z) {
    vspi.beginTransaction(AJUSTES);
    digitalWrite(PIN_ADXL_CS, LOW);
    vspi.transfer(0x32 | 0xC0);   // lectura multibyte desde DATAX0
    int16_t v[3];
    for (int i = 0; i < 3; i++) {
        const uint8_t lo = vspi.transfer(0), hi = vspi.transfer(0);
        v[i] = (int16_t)(lo | (hi << 8));
    }
    digitalWrite(PIN_ADXL_CS, HIGH);
    vspi.endTransaction();
    x = v[0] * 0.0039f; y = v[1] * 0.0039f; z = v[2] * 0.0039f;
}

void setup() {
    encabezado("ADXL345 (SPI)");
    pinMode(PIN_ADXL_CS, OUTPUT);
    digitalWrite(PIN_ADXL_CS, HIGH);
    pinMode(PIN_ADXL_INT1, INPUT);
    vspi.begin(PIN_ADXL_SCK, PIN_ADXL_MISO, PIN_ADXL_MOSI, PIN_ADXL_CS);

    const uint8_t id = leer(0x00);
    Serial.printf("  DEVID = 0x%02X (esperado 0xE5)\n", id);
    verificar(id == 0xE5, "DEVID = 0xE5",
              id == 0x00 || id == 0xFF ? "no responde: revisar CS=4, SCK=18, MISO=19, MOSI=23, 3V3 y GND (algunos GY-291 traen SPI de 3 hilos: SDO al MISO)"
                                       : "responde algo raro: cables cruzados o módulo dañado");

    escribir(0x2D, 0x00);
    escribir(0x31, 0x0B);   // resolución completa, ±16 g
    escribir(0x2C, 0x0B);   // 200 Hz
    escribir(0x2F, 0x00);   // interrupciones a INT1
    escribir(0x2E, 0x80);   // DATA_READY
    escribir(0x2D, 0x08);   // medición
    verificar(leer(0x31) == 0x0B && leer(0x2C) == 0x0B, "escribe y relee la configuración");

    delay(100);
    float sx = 0, sy = 0, sz = 0, mn = 99, mx = 0;
    for (int i = 0; i < 100; i++) {
        float x, y, z;
        leerXYZ(x, y, z);
        const float m = sqrtf(x * x + y * y + z * z);
        sx += x; sy += y; sz += z;
        mn = min(mn, m); mx = max(mx, m);
        delay(5);
    }
    const float mag = sqrtf(sx * sx + sy * sy + sz * sz) / 100;
    Serial.printf("  promedio x=%.3f y=%.3f z=%.3f g · |a| = %.3f g (min %.3f, max %.3f)\n", sx / 100, sy / 100, sz / 100,
                  mag, mn, mx);
    verificar(mag > 0.85f && mag < 1.15f, "en reposo |a| ≈ 1 g (0,85–1,15)", "si da 0 o algo fijo: no está midiendo");
    verificar(mx - mn < 0.15f, "ruido en reposo < 0,15 g", "¿se movió durante la prueba?");

    // INT1: con DATA_READY activo debe cambiar de nivel varias veces en 200 ms
    int cambios = 0, anterior = digitalRead(PIN_ADXL_INT1);
    const uint32_t t0 = millis();
    while (millis() - t0 < 200) {
        const int ahora = digitalRead(PIN_ADXL_INT1);
        if (ahora != anterior) { cambios++; anterior = ahora; }
        if (ahora) { float x, y, z; leerXYZ(x, y, z); }   // leer limpia DATA_READY
    }
    Serial.printf("  INT1 cambió %d veces en 200 ms\n", cambios);
    verificar(cambios >= 10, "INT1 (GPIO 34) se activa con DATA_READY", "revisar el cable INT1 → GPIO 34");
    resultadoFinal("ADXL345");
}

void loop() {}
