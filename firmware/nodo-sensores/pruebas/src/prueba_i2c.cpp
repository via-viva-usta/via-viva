// Escáner I2C: lista las direcciones que responden en SDA 21 / SCL 22.
// Se esperan 0x68 (MPU-6050; 0x69 si AD0 está en alto) y 0x29 (VL53L0X).
#include <Wire.h>

#include "pines.h"
#include "resultado.h"

void setup() {
    encabezado("escaner I2C");
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 100000);   // 100 kHz para el escaneo: tolera cables largos
    bool hay68 = false, hay69 = false, hay29 = false;
    int total = 0;
    for (uint8_t dir = 1; dir < 127; dir++) {
        Wire.beginTransmission(dir);
        if (Wire.endTransmission() == 0) {
            Serial.printf("  dispositivo en 0x%02X\n", dir);
            total++;
            hay68 |= dir == 0x68;
            hay69 |= dir == 0x69;
            hay29 |= dir == 0x29;
        }
    }
    verificar(total > 0, "algún dispositivo responde",
              "revisar 3V3, GND, SDA=21, SCL=22; ¿módulos sin resistencias pull-up?");
    verificar(hay68 || hay69, "MPU-6050 en 0x68 (o 0x69)", "revisar el MPU-6050; si sale 0x69, AD0 está en alto");
    verificar(hay29, "VL53L0X en 0x29", "revisar el VL53L0X (XSHUT debe quedar suelto o en alto)");
    resultadoFinal("I2C");
}

void loop() {}
