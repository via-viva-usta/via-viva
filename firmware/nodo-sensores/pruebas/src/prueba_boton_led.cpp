// Prueba del pulsador de etiquetado (GPIO 26 a GND, pull-up interno) y del LED de estado (GPIO 33).
// Instrucciones: el LED parpadea 3 veces (míralo); luego oprime el pulsador 3 veces en los siguientes 20 s.
// Cada pulsación enciende el LED medio segundo.
#include "pines.h"
#include "resultado.h"

void setup() {
    encabezado("pulsador + LED");
    pinMode(PIN_LED, OUTPUT);
    pinMode(PIN_PULSADOR, INPUT_PULLUP);

    Serial.println("  El LED (GPIO 33) debe parpadear 3 veces ahora...");
    for (int i = 0; i < 3; i++) {
        digitalWrite(PIN_LED, HIGH); delay(300);
        digitalWrite(PIN_LED, LOW); delay(300);
    }
    Serial.println("  (El LED no se puede verificar solo: si no parpadeó, revisar polaridad y la resistencia de 220–330 Ω.)");

    verificar(digitalRead(PIN_PULSADOR) == HIGH, "pulsador en reposo = ALTO (pull-up)",
              "lee BAJO sin oprimir: el pulsador está en corto o cableado a 3V3 en vez de a GND");

    Serial.println("  Oprime el pulsador 3 veces (20 s)...");
    int pulsaciones = 0, rebotes = 0;
    int anterior = HIGH;
    uint32_t ultimo = 0;
    const uint32_t t0 = millis();
    while (millis() - t0 < 20000 && pulsaciones < 3) {
        const int ahora = digitalRead(PIN_PULSADOR);
        if (anterior == HIGH && ahora == LOW) {
            if (millis() - ultimo > 250) {          // mismo antirrebote que el firmware
                pulsaciones++;
                Serial.printf("  pulsación %d\n", pulsaciones);
                digitalWrite(PIN_LED, HIGH);
                delay(500);
                digitalWrite(PIN_LED, LOW);
            } else {
                rebotes++;
            }
            ultimo = millis();
        }
        anterior = ahora;
    }
    Serial.printf("  rebotes filtrados: %d\n", rebotes);
    verificar(pulsaciones == 3, "se detectan las 3 pulsaciones", "revisar el pulsador entre GPIO 26 y GND");
    resultadoFinal("pulsador + LED");
}

void loop() {}
