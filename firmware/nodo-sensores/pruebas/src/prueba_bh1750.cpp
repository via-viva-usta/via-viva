// Prueba del BH1750 (luz) por I2C (SDA 21, SCL 22, dirección 0x23 con ADDR a GND; 0x5C con ADDR en alto).
// Usa el mismo controlador del nodo (include/ambiente.h).
// Pide TAPAR el sensor con el dedo y luego DESTAPARLO: la luz debe bajar y subir.
#include <Wire.h>

#include "ambiente.h"
#include "pines.h"
#include "resultado.h"

static BH1750 bh;

static float promedio(int n) {
    float suma = 0, lux;
    int ok = 0;
    for (int i = 0; i < n; i++) {
        delay(180);   // medida de alta resolución: 120 ms típico, 180 ms máximo
        if (bh.leer(lux)) { suma += lux; ok++; }
    }
    return ok ? suma / ok : NAN;
}

void setup() {
    encabezado("BH1750 (luz, I2C)");
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 100000);
    bool ok = bh.iniciar(Wire, 0x23);
    if (!ok) ok = bh.iniciar(Wire, 0x5C);
    Serial.printf("  dirección probada: 0x%02X\n", bh.direccion());
    verificar(ok, "responde en 0x23 (o 0x5C)", "correr la prueba i2c; revisar VCC, GND, SDA=21, SCL=22 y ADDR");
    if (!ok) { resultadoFinal("BH1750"); return; }
    if (bh.direccion() != 0x23) Serial.println("  OJO: el nodo espera 0x23 (BH1750_DIR en config.h): poner ADDR a GND");

    const float destapado = promedio(5);
    Serial.printf("  luz ambiente: %.1f lx\n", destapado);
    verificar(!isnan(destapado) && destapado < 65535 / 1.2f, "lecturas válidas");

    Serial.println("  >> TAPA el sensor con el dedo (tienes 5 s)...");
    delay(5000);
    const float tapado = promedio(5);
    Serial.printf("  tapado: %.1f lx\n", tapado);
    Serial.println("  >> DESTÁPALO (5 s)...");
    delay(5000);
    const float otraVez = promedio(5);
    Serial.printf("  destapado otra vez: %.1f lx\n", otraVez);
    verificar(tapado < 0.5f * otraVez || (otraVez < 5 && tapado < 2), "tapar el sensor baja la luz a menos de la mitad",
              "¿se tapó de verdad? si el cuarto está oscuro, encender la luz y repetir");
    resultadoFinal("BH1750");
}

void loop() {
    float lux;
    if (bh.leer(lux)) Serial.printf("%.1f lx\n", lux);
    delay(1000);
}
