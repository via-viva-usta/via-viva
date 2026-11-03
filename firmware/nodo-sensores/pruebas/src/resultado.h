// Utilidades comunes de los programas de prueba: líneas PASA/FALLA claras por el monitor serie.
#pragma once
#include <Arduino.h>

static int fallas = 0;

inline void verificar(bool ok, const char* que, const char* pista = "") {
    Serial.printf("  [%s] %s", ok ? "PASA " : "FALLA", que);
    if (!ok && pista[0]) Serial.printf("  → %s", pista);
    Serial.println();
    if (!ok) fallas++;
}

inline void resultadoFinal(const char* sensor) {
    Serial.println("------------------------------------------------------------");
    if (fallas == 0) Serial.printf("RESULTADO %s: PASA\n", sensor);
    else Serial.printf("RESULTADO %s: FALLA (%d verificación(es) no pasaron; ver pistas arriba)\n", sensor, fallas);
    Serial.println("------------------------------------------------------------");
}

inline void encabezado(const char* sensor) {
    Serial.begin(115200);
    delay(1500);
    Serial.printf("\n=== Prueba: %s ===\n", sensor);
}
