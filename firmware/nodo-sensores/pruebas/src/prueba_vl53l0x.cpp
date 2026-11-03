// Prueba del VL53L0X (láser ToF, I2C 0x29). Apuntarlo a una superficie fija a 10–100 cm (mesa, pared) y no moverlo.
// Después imprime la distancia cada 0,5 s: probar también al sol (el alcance cae con luz fuerte).
#include <VL53L0X.h>
#include <Wire.h>

#include "pines.h"
#include "resultado.h"

static VL53L0X tof;

void setup() {
    encabezado("VL53L0X (láser)");
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 400000);
    tof.setTimeout(200);
    const bool ok = tof.init();
    verificar(ok, "inicia", "no responde: correr primero la prueba i2c; XSHUT suelto o en alto");
    if (ok) {
        tof.setMeasurementTimingBudget(20000);
        tof.startContinuous();
        float suma = 0, suma2 = 0;
        int validas = 0, timeouts = 0;
        for (int i = 0; i < 50; i++) {
            const uint16_t d = tof.readRangeContinuousMillimeters();
            if (tof.timeoutOccurred()) { timeouts++; continue; }
            if (d > 30 && d < 2000) { validas++; suma += d; suma2 += (float)d * d; }
        }
        const float media = validas ? suma / validas : 0;
        const float desv = validas > 1 ? sqrtf(max(0.0f, suma2 / validas - media * media)) : 0;
        Serial.printf("  %d lecturas válidas de 50 · %d timeouts · media %.0f mm · desviación %.1f mm\n", validas, timeouts,
                      media, desv);
        verificar(timeouts == 0, "sin timeouts", "cable I2C largo: bajar a 100 kHz o acortar");
        verificar(validas >= 45, "≥ 45 lecturas en rango (30–2000 mm)", "nada al frente o fuera de rango; ¿mucho sol?");
        verificar(validas > 1 && desv < 15, "desviación < 15 mm con el sensor quieto", "superficie oscura/brillante o vibración");
    }
    resultadoFinal("VL53L0X");
}

void loop() {
    const uint16_t d = tof.readRangeContinuousMillimeters();
    Serial.printf("distancia = %u mm%s\n", d, tof.timeoutOccurred() ? " (timeout)" : "");
    delay(500);
}
