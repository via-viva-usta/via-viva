// Prueba del BME280 por I2C (SDA 21, SCL 22, dirección 0x76; 0x77 si SDO está en alto).
// Usa el mismo controlador del nodo (include/ambiente.h).
// 1. Autoprueba de la fórmula de compensación con el ejemplo de la hoja de datos de Bosch (no necesita el sensor).
// 2. ID del chip: 0x60 = BME280; 0x58 = BMP280 (muchos módulos "BME280" baratos lo son y NO miden humedad).
// 3. 10 lecturas: rangos razonables para Tunja (≈ 2 800 m: presión ≈ 730-760 hPa) y estabilidad.
// Después imprime una lectura cada 2 s: soplar sobre el sensor debe subir la humedad y la temperatura.
#include <Wire.h>

#include "ambiente.h"
#include "pines.h"
#include "resultado.h"

static BME280 bme;

static void autopruebaFormula() {
    BME280 e;   // valores del ejemplo de la hoja de datos (BMP280, sección 3.12)
    e.T1 = 27504; e.T2 = 26435; e.T3 = -1000;
    e.P1 = 36477; e.P2 = -10685; e.P3 = 3024; e.P4 = 2855; e.P5 = 140; e.P6 = -7; e.P7 = 15500; e.P8 = -14600; e.P9 = 6000;
    const int32_t t = e.compensarT(519888);
    const float p = e.compensarP(415148) / 256.0f;
    Serial.printf("  ejemplo de la hoja de datos: T = %.2f °C (esperado 25,08) · P = %.2f Pa (esperado ≈ 100 653)\n",
                  t / 100.0f, p);
    verificar(t == 2508 && fabsf(p - 100653.27f) < 1.0f, "fórmula de compensación (sin sensor)",
              "el controlador está mal: no seguir");
}

void setup() {
    encabezado("BME280 (I2C)");
    autopruebaFormula();
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 100000);
    const bool ok = bme.iniciar(Wire);
    Serial.printf("  dirección 0x%02X · ID del chip = 0x%02X\n", bme.direccion(), bme.chipId());
    verificar(ok, "responde en 0x76 o 0x77 con ID 0x60/0x58",
              "correr la prueba i2c; revisar 3V3 (no 5 V si el módulo no tiene regulador), SDA=21, SCL=22");
    if (!ok) { resultadoFinal("BME280"); return; }
    verificar(bme.tieneHumedad(), "es BME280 (mide humedad)",
              "es un BMP280: sirve para temperatura y presión; para humedad usar el DHT22 (prueba dht22)");

    delay(1200);   // primera medida en modo normal (reposo de 1 s)
    float tMin = 99, tMax = -99, t, h, p, hUlt = NAN, pUlt = NAN;
    int buenas = 0;
    for (int i = 0; i < 10; i++) {
        if (bme.leer(t, h, p)) {
            buenas++;
            tMin = min(tMin, t);
            tMax = max(tMax, t);
            hUlt = h;
            pUlt = p;
            Serial.printf("  %2d: %.2f °C · %.1f %% HR · %.2f hPa\n", i + 1, t, h, p);
        }
        delay(1100);
    }
    verificar(buenas == 10, "10 lecturas sin error de bus");
    if (buenas) {
        verificar(tMin > -5 && tMax < 45, "temperatura entre -5 y 45 °C");
        verificar(tMax - tMin < 1.0f, "temperatura estable en reposo (variación < 1 °C)");
        verificar(pUlt > 650 && pUlt < 1050, "presión entre 650 y 1050 hPa",
                  "en Tunja se espera ≈ 730-760 hPa; fuera de rango = calibración mal leída");
        if (bme.tieneHumedad()) verificar(hUlt > 5 && hUlt < 100, "humedad entre 5 y 100 %");
    }
    resultadoFinal("BME280");
    Serial.println("\nAhora sopla sobre el sensor: la humedad y la temperatura deben subir.");
}

void loop() {
    float t, h, p;
    if (bme.chipId() && bme.leer(t, h, p)) Serial.printf("%.2f °C · %.1f %% HR · %.2f hPa\n", t, h, p);
    delay(2000);
}
