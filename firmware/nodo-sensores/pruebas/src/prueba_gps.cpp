// Prueba del GPS NEO-6M por UART2 (TX del GPS → GPIO 16, RX del GPS ← GPIO 17), 9600 baud.
// Las dos primeras verificaciones (llegan datos y frases NMEA válidas) pasan bajo techo.
// La fijación necesita CIELO ABIERTO: en frío puede tardar 1–5 minutos. Se esperan hasta 5 minutos.
#include <TinyGPSPlus.h>

#include "pines.h"
#include "resultado.h"

static TinyGPSPlus gps;

void setup() {
    encabezado("GPS NEO-6M (UART2)");
    Serial2.begin(9600, SERIAL_8N1, PIN_GPS_RX, PIN_GPS_TX);

    uint32_t bytes = 0;
    const uint32_t t0 = millis();
    while (millis() - t0 < 5000) {
        while (Serial2.available()) { gps.encode(Serial2.read()); bytes++; }
    }
    Serial.printf("  %lu bytes en 5 s · frases válidas %lu · con error de suma %lu\n", (unsigned long)bytes,
                  (unsigned long)gps.passedChecksum(), (unsigned long)gps.failedChecksum());
    verificar(bytes > 500, "llegan datos por UART2",
              bytes == 0 ? "nada: TX del GPS debe ir al GPIO 16; revisar VCC (3,3–5 V según el módulo) y GND"
                         : "llega poco: ¿velocidad distinta de 9600?");
    verificar(gps.passedChecksum() > 3 && gps.failedChecksum() <= gps.passedChecksum() / 10, "frases NMEA válidas",
              "basura: velocidad en baudios equivocada o ruido en el cable");

    Serial.println("  Esperando fijación (hasta 5 min; el LED del módulo parpadea cuando la tiene)...");
    const uint32_t t1 = millis();
    while (millis() - t1 < 300000 && !(gps.location.isValid() && gps.location.age() < 2000)) {
        while (Serial2.available()) gps.encode(Serial2.read());
        static uint32_t ultimo = 0;
        if (millis() - ultimo > 10000) {
            ultimo = millis();
            Serial.printf("  ... %lu s · satélites visibles: %u\n", (unsigned long)((millis() - t1) / 1000),
                          gps.satellites.isValid() ? gps.satellites.value() : 0);
        }
    }
    const bool fijo = gps.location.isValid();
    if (fijo) {
        Serial.printf("  Fijación en %lu s: %.6f, %.6f · %u satélites · HDOP %.1f · %02d:%02d:%02d UTC\n",
                      (unsigned long)((millis() - t1) / 1000), gps.location.lat(), gps.location.lng(),
                      gps.satellites.value(), gps.hdop.hdop(), gps.time.hour(), gps.time.minute(), gps.time.second());
    }
    verificar(fijo, "fijación de posición en < 5 min", "bajo techo NO hay señal: salir a cielo abierto; antena hacia arriba");
    resultadoFinal("GPS");
}

void loop() {
    while (Serial2.available()) gps.encode(Serial2.read());
    static uint32_t ultimo = 0;
    if (millis() - ultimo > 1000) {
        ultimo = millis();
        if (gps.location.isValid())
            Serial.printf("%.6f, %.6f · %.1f km/h · %u sat\n", gps.location.lat(), gps.location.lng(), gps.speed.kmph(),
                          gps.satellites.value());
    }
}
