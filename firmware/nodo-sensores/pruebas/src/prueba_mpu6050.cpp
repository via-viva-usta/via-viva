// Prueba del MPU-6050 por I2C (SDA 21, SCL 22, dirección 0x68). Dejarlo QUIETO durante la prueba.
// Después imprime el giro en Z cada 0,5 s: girar el módulo a la izquierda (antihorario visto desde arriba)
// debe dar valores POSITIVOS — así se confirma el signo que usa el detector de maniobras.
#include <Wire.h>

#include "pines.h"
#include "resultado.h"

uint8_t leer(uint8_t reg) {
    Wire.beginTransmission(0x68);
    Wire.write(reg);
    if (Wire.endTransmission(false) != 0) return 0xFF;
    Wire.requestFrom(0x68, 1);
    return Wire.available() ? Wire.read() : 0xFF;
}

void escribir(uint8_t reg, uint8_t v) {
    Wire.beginTransmission(0x68);
    Wire.write(reg);
    Wire.write(v);
    Wire.endTransmission();
}

bool leerTodo(float a[3], float g[3], uint32_t& us) {
    const uint32_t t0 = micros();
    Wire.beginTransmission(0x68);
    Wire.write(0x3B);
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom(0x68, 14) != 14) return false;
    uint8_t b[14];
    for (int i = 0; i < 14; i++) b[i] = Wire.read();
    us = micros() - t0;
    for (int i = 0; i < 3; i++) {
        a[i] = (int16_t)((b[2 * i] << 8) | b[2 * i + 1]) / 4096.0f;      // ±8 g
        g[i] = (int16_t)((b[8 + 2 * i] << 8) | b[9 + 2 * i]) / 65.5f;    // ±500 °/s
    }
    return true;
}

void setup() {
    encabezado("MPU-6050 (I2C)");
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 400000);
    const uint8_t quien = leer(0x75);
    Serial.printf("  WHO_AM_I = 0x%02X (esperado 0x68)\n", quien);
    verificar(quien == 0x68 || quien == 0x70 || quien == 0x72, "WHO_AM_I responde",
              quien == 0xFF ? "no responde: correr primero la prueba i2c" : "otro chip (algunos clones dicen 0x70/0x72 y sirven)");
    escribir(0x6B, 0x01);
    escribir(0x1B, 0x08);
    escribir(0x1C, 0x10);
    delay(100);

    float sa[3] = {0}, sg[3] = {0}, a[3], g[3];
    uint32_t us = 0, usMax = 0, usSuma = 0;
    int ok = 0;
    for (int i = 0; i < 100; i++) {
        if (leerTodo(a, g, us)) {
            ok++;
            usSuma += us;
            usMax = max(usMax, us);
            for (int k = 0; k < 3; k++) { sa[k] += a[k]; sg[k] += g[k]; }
        }
        delay(10);
    }
    verificar(ok == 100, "100 lecturas seguidas sin error");
    if (ok) {
        const float mag = sqrtf(sa[0] * sa[0] + sa[1] * sa[1] + sa[2] * sa[2]) / ok;
        Serial.printf("  |a| = %.3f g · giro promedio = (%.2f, %.2f, %.2f) °/s · lectura de 14 bytes: %lu µs promedio, %lu máx\n",
                      mag, sg[0] / ok, sg[1] / ok, sg[2] / ok, (unsigned long)(usSuma / ok), (unsigned long)usMax);
        verificar(mag > 0.85f && mag < 1.15f, "en reposo |a| ≈ 1 g");
        verificar(fabsf(sg[0] / ok) < 5 && fabsf(sg[1] / ok) < 5 && fabsf(sg[2] / ok) < 5, "giro en reposo < 5 °/s",
                  "desfase alto: se puede restar en el firmware; si es enorme, el módulo está dañado");
    }
    resultadoFinal("MPU-6050");
    Serial.println("\nAhora gira el módulo sobre la mesa: izquierda (antihorario) debe dar giro Z POSITIVO.");
}

void loop() {
    float a[3], g[3];
    uint32_t us;
    if (leerTodo(a, g, us)) Serial.printf("giro Z = %7.1f °/s   (X adelante: aceleración X = %5.2f g)\n", g[2], a[0]);
    delay(500);
}
