// VÍA VIVA — nodo de sensores (ESP32 DevKit de 30 pines, WROOM-32, entorno esp32dev)
//
// Reparto de tareas (FreeRTOS, doble núcleo):
//   Núcleo 1 (APP_CPU): tareaAdquisicion (ADXL345 por VSPI + DMA) → búfer ping-pong → tareaProcesamiento
//                       (detector por umbrales → características → clase → evento)
//   Núcleo 0 (PRO_CPU): Wi-Fi + página web, GPS, I2C (MPU-6050 + VL53L0X + maniobras + ambiente), microSD, estadísticas
//
// Archivos: adquisicion.cpp, procesamiento.cpp, perifericos.cpp (GPS, I2C y ambiente), registro.cpp (microSD),
// servidor_web.cpp + ajustes.cpp (página y umbrales en la flash), estadisticas.cpp, led_estado.cpp (códigos del LED). Lo que solo se puede validar con la placa real está marcado [VALIDAR EN PLACA].

#include <Arduino.h>

#include "ajustes.h"
#include "esp_system.h"
#include "esp_task_wdt.h"
#include "esp_timer.h"
#include "estado.h"
#include "experimentos.h"
#include "pines.h"

// ---- Estado global (declarado en estado.h) ----
ADXL345 adxl;
EstadoGPS estadoGPS;
EstadoI2C estadoI2C;
EstadoNodo estadoNodo;
SemaphoreHandle_t mutexGPS, mutexI2C, mutexNodo;
Bloque pingPong[2];
SemaphoreHandle_t mitadLibre[2];
QueueHandle_t colaBloques, colaCrudo, colaEventosSD, colaGpsSD, colaEtiquetas, colaAmbienteSD;
TaskHandle_t hAdquisicion;

EstadoGPS copiarGPS() {
    EstadoGPS e;
    if (xSemaphoreTake(mutexGPS, pdMS_TO_TICKS(5)) == pdTRUE) {
        e = estadoGPS;
        xSemaphoreGive(mutexGPS);
    }
    return e;
}

EstadoI2C copiarI2C() {
    EstadoI2C e;
    if (xSemaphoreTake(mutexI2C, pdMS_TO_TICKS(5)) == pdTRUE) {
        e = estadoI2C;
        xSemaphoreGive(mutexI2C);
    }
    return e;
}

EstadoNodo copiarNodo() {
    EstadoNodo e;
    if (xSemaphoreTake(mutexNodo, pdMS_TO_TICKS(5)) == pdTRUE) {
        e = estadoNodo;
        xSemaphoreGive(mutexNodo);
    }
    return e;
}

// Etiquetas de campo: del pulsador (ISR) o de los botones de la página web.
void registrarEtiqueta(int64_t tUs, const char* tipo, const char* origen) {
    Etiqueta e{};
    e.tUs = tUs;
    strncpy(e.tipo, tipo, sizeof(e.tipo) - 1);
    strncpy(e.origen, origen, sizeof(e.origen) - 1);
    xQueueSend(colaEtiquetas, &e, 0);
}

static void IRAM_ATTR isrPulsador() {
    static int64_t ultimo = 0;
    const int64_t t = esp_timer_get_time();
    if (t - ultimo < (int64_t)ANTIRREBOTE_MS * 1000) return;
    ultimo = t;
    Etiqueta e{};
    e.tUs = t;
    memcpy(e.tipo, "boton", 6);
    memcpy(e.origen, "boton", 6);
    BaseType_t despertar = pdFALSE;
    xQueueSendFromISR(colaEtiquetas, &e, &despertar);
    portYIELD_FROM_ISR(despertar);
}

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.println("\n=== VÍA VIVA · nodo de sensores (ESP32 WROOM-32) ===");
    Serial.printf("Modo de adquisición (E1): %d · fs = %u Hz · watermark = %u\n", MODO_ADQ, FS_HZ, FIFO_WATERMARK);
    // [VALIDAR EN PLACA] La WROOM-32 debe mostrar 4 MB de flash (no tiene PSRAM)
    Serial.printf("Flash: %u B · heap libre: %u B · programa: %u B\n", ESP.getFlashChipSize(), ESP.getFreeHeap(),
                  ESP.getSketchSize());

    pinMode(PIN_LED, OUTPUT);
    digitalWrite(PIN_LED, HIGH);   // encendido fijo = arrancando (después lo maneja tareaLED, src/led_estado.cpp)
    pinMode(PIN_PULSADOR, INPUT_PULLUP);
    pinMode(PIN_ADXL_INT1, INPUT);

    mutexGPS = xSemaphoreCreateMutex();
    mutexI2C = xSemaphoreCreateMutex();
    mutexNodo = xSemaphoreCreateMutex();
    for (int i = 0; i < 2; i++) {
        mitadLibre[i] = xSemaphoreCreateBinary();
        xSemaphoreGive(mitadLibre[i]);
    }
    colaBloques = xQueueCreate(2, sizeof(int));
    colaCrudo = xQueueCreate(16, sizeof(Bloque));   // 2,5 s de margen si la tarjeta o la descarga por Wi-Fi demoran
    colaEventosSD = xQueueCreate(8, sizeof(Evento));
    colaGpsSD = xQueueCreate(8, sizeof(EstadoGPS));
    colaEtiquetas = xQueueCreate(8, sizeof(Etiqueta));
    colaAmbienteSD = xQueueCreate(4, sizeof(FilaAmbiente));
    colaExp = xQueueCreate(64, sizeof(FilaExp));

    // Causa del último reinicio: si fue el watchdog o un bajo voltaje, queda en exp_NNN.csv y en la página web
    estadoNodo.causaReinicio = (int)esp_reset_reason();
    Serial.printf("Causa del reinicio: %d (1 = encendido, 4 = error, 5-7 = watchdog, 9 = bajo voltaje)\n",
                  estadoNodo.causaReinicio);
    registrarExp("ARR", "arranque", "causa_reinicio", estadoNodo.causaReinicio);
    cargarAjustes();   // umbrales del detector guardados desde la página (flash/NVS); si no hay, los de config.h

    // Watchdog de tareas: las tareas críticas se suscriben; si una se cuelga WDT_TAREAS_S, el nodo se reinicia
    // (y empieza una sesión nueva en la microSD). El Arduino ya lo deja con 5 s; aquí se pasa a 10 s con reinicio.
    esp_task_wdt_init(WDT_TAREAS_S, true);

    iniciarMedicionOcio();   // 1 s sin tareas propias: referencia para el % de CPU

    // ---- ADXL345 (VSPI + DMA) ----
    // [VALIDAR EN PLACA] DEVID = 0xE5 y lectura de vuelta de la configuración
    const bool adxlOk = adxl.iniciar(PIN_ADXL_SCK, PIN_ADXL_MOSI, PIN_ADXL_MISO, PIN_ADXL_CS, SPI_ADXL_HZ);
    const bool cfgOk = adxlOk && adxl.configurar(FS_HZ, MODO_ADQ, FIFO_WATERMARK);
    Serial.printf("[ADXL345] DEVID=0x%02X (%s) · configuración %s\n", adxl.devid(),
                  adxlOk ? "OK" : "NO RESPONDE", cfgOk ? "OK" : "FALLÓ");

    // ---- microSD (HSPI por la matriz GPIO, src/registro.cpp) ----
    // Aquí se elige la sesión (escribe el contador en la flash) antes de que corra la adquisición.
    const bool sdOk = iniciarSD();
    Serial.printf("[SD] %s\n", sdOk ? "OK" : "NO DETECTADA (se reintenta cada 10 s; mientras tanto no se guarda)");
    estadoNodo.adxlOk = adxlOk && cfgOk;

    // ---- E2, E3, E4 y memoria: se miden ahora, sin tareas propias que interfieran ----
    if (estadoNodo.adxlOk) experimentosArranque();

    // ---- UART ----
    Serial2.begin(GPS_BAUD, SERIAL_8N1, PIN_GPS_RX, PIN_GPS_TX);   // UART2: GPS

    // ---- Tareas: adquisición y procesamiento en el núcleo 1; Wi-Fi y lo demás en el núcleo 0 ----
    xTaskCreatePinnedToCore(tareaAdquisicion, "adq", 4096, nullptr, 20, &hAdquisicion, 1);
    xTaskCreatePinnedToCore(tareaProcesamiento, "proc", 8192, nullptr, 10, nullptr, 1);
    xTaskCreatePinnedToCore(tareaGPS, "gps", 4096, nullptr, 8, nullptr, 0);
    xTaskCreatePinnedToCore(tareaI2C, "i2c", 4096, nullptr, 7, nullptr, 0);
    xTaskCreatePinnedToCore(tareaRegistro, "sd", 8192, nullptr, 4, nullptr, 0);
    xTaskCreatePinnedToCore(tareaWeb, "web", 8192, nullptr, 3, nullptr, 0);
    xTaskCreatePinnedToCore(tareaEstadisticas, "stats", 4096, nullptr, 2, nullptr, 0);
    xTaskCreatePinnedToCore(tareaLED, "led", 2048, nullptr, 1, nullptr, 0);
    // Con watchdog: adq, proc, gps, i2c y sd. Sin watchdog: web (una descarga larga la ocupa), stats y led.

    if (MODO_ADQ != MODO_ADQ_POLLING) attachInterrupt(PIN_ADXL_INT1, isrAdxl, RISING);
    attachInterrupt(PIN_PULSADOR, isrPulsador, FALLING);
}

void loop() {
    vTaskDelete(nullptr);   // todo corre en tareas; así el núcleo 1 queda libre para medir su ocio
}
