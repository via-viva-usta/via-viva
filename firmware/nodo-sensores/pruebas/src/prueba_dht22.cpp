// Prueba del DHT22 (AM2302) en GPIO 25 (PIN_DHT22), solo si no hay BME280.
// Usa el mismo controlador del nodo (include/ambiente.h). Pull-up de 10 kΩ a 3V3 (el módulo de 3 pines ya la trae).
// 10 lecturas cada 2,5 s: cuenta errores (sin respuesta, tiempo de bit, suma) y revisa rangos y estabilidad.
#include <Wire.h>   // la necesita ambiente.h (el buscador de librerías de PlatformIO no mira ../include)

#include "ambiente.h"
#include "pines.h"
#include "resultado.h"

static DHT22 dht;

void setup() {
    encabezado("DHT22 (un hilo, GPIO 25)");
    dht.iniciar(PIN_DHT22);
    delay(2000);   // el sensor necesita ~1-2 s después de energizarse

    int buenas = 0, sinRespuesta = 0;
    float tMin = 99, tMax = -99, hUlt = NAN, t, h;
    for (int i = 0; i < 10; i++) {
        const DHT22::Error e = dht.leer(t, h);
        if (e == DHT22::OK) {
            buenas++;
            tMin = min(tMin, t);
            tMax = max(tMax, t);
            hUlt = h;
            Serial.printf("  %2d: %.1f °C · %.1f %% HR\n", i + 1, t, h);
        } else {
            if (e == DHT22::SIN_RESPUESTA) sinRespuesta++;
            Serial.printf("  %2d: error (%s)\n", i + 1, DHT22::nombreError(e));
        }
        delay(2500);
    }
    verificar(buenas > 0, "el sensor responde",
              sinRespuesta ? "sin respuesta: revisar DATA en GPIO 25, 3V3, GND y la pull-up de 10 kΩ" : "");
    verificar(buenas >= 8, "al menos 8 de 10 lecturas correctas",
              "errores de suma o de tiempo: cable largo o sin pull-up; acortar el cable");
    if (buenas) {
        verificar(tMin > -5 && tMax < 45, "temperatura entre -5 y 45 °C");
        verificar(tMax - tMin < 1.0f, "temperatura estable en reposo (variación < 1 °C)");
        verificar(hUlt > 5 && hUlt < 100, "humedad entre 5 y 100 %");
    }
    resultadoFinal("DHT22");
    Serial.println("\nAhora sopla sobre el sensor: la humedad debe subir en pocos segundos.");
}

void loop() {
    float t, h;
    const DHT22::Error e = dht.leer(t, h);
    if (e == DHT22::OK) Serial.printf("%.1f °C · %.1f %% HR\n", t, h);
    else Serial.printf("error: %s\n", DHT22::nombreError(e));
    delay(2500);
}
