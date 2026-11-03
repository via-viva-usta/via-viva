// VÍA VIVA — nodo de cámara (ESP32-CAM AI-Thinker, OV2640)
//
// Espera órdenes del nodo de sensores (ESP32 WROOM-32) por UART y responde (docs/diagramas/01_arquitectura.md):
//   "PING"              → "PONG"
//   "FOTO,<id>,<hora>"  → captura → difumina → JPEG en PSRAM → "OK,<id>,<bytes>" o "ERR,<id>,<codigo>"
//
// ESQUELETO. Lo que falta o hay que validar con la placa real está marcado con [PENDIENTE] / [VALIDAR EN PLACA].
// Privacidad: la imagen original nunca sale de este nodo; solo se conserva la versión difuminada.

#include <Arduino.h>

#include "esp_camera.h"
#include "img_converters.h"

// ---- Enlace UART con el nodo de sensores (ESP32 WROOM-32) ----
// [VALIDAR EN PLACA] CLAUDE.md deja como candidatos 13/14 o 14/15 (pines de la microSD interna, que no se usa).
// Se elige RX = 13 y TX = 14: el GPIO 14 emite una señal al arrancar, y como TX solo manda
// basura al nodo (que la descarta); como RX pelearía con el TX del nodo. Poner 1 kΩ en serie en cada línea.
#define PIN_ENLACE_RX 13   // ← GPIO 25 (TX) del nodo de sensores
#define PIN_ENLACE_TX 14   // → GPIO 35 (RX) del nodo de sensores
#define ENLACE_BAUD 115200
#define PIN_FLASH 4        // LED de flash: apagado (deslumbra a otros conductores)

// ---- Pines de la cámara en la AI-Thinker ----
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

static constexpr int RADIO_DIFUMINADO = 6;   // píxeles; provisional

static uint8_t* ultimaFoto = nullptr;        // JPEG difuminado más reciente (PSRAM)
static size_t ultimaFotoBytes = 0;

static bool iniciarCamara() {
    camera_config_t c = {};
    c.ledc_channel = LEDC_CHANNEL_0;
    c.ledc_timer = LEDC_TIMER_0;
    c.pin_d0 = Y2_GPIO_NUM;
    c.pin_d1 = Y3_GPIO_NUM;
    c.pin_d2 = Y4_GPIO_NUM;
    c.pin_d3 = Y5_GPIO_NUM;
    c.pin_d4 = Y6_GPIO_NUM;
    c.pin_d5 = Y7_GPIO_NUM;
    c.pin_d6 = Y8_GPIO_NUM;
    c.pin_d7 = Y9_GPIO_NUM;
    c.pin_xclk = XCLK_GPIO_NUM;
    c.pin_pclk = PCLK_GPIO_NUM;
    c.pin_vsync = VSYNC_GPIO_NUM;
    c.pin_href = HREF_GPIO_NUM;
    c.pin_sccb_sda = SIOD_GPIO_NUM;
    c.pin_sccb_scl = SIOC_GPIO_NUM;
    c.pin_pwdn = PWDN_GPIO_NUM;
    c.pin_reset = RESET_GPIO_NUM;
    c.xclk_freq_hz = 20000000;
    // Escala de grises QVGA: se puede difuminar sin decodificar JPEG.
    // [PENDIENTE] pasar a color y mayor resolución cuando exista el difuminado selectivo.
    c.pixel_format = PIXFORMAT_GRAYSCALE;
    c.frame_size = FRAMESIZE_QVGA;           // 320 × 240
    c.fb_location = CAMERA_FB_IN_PSRAM;
    c.fb_count = 1;
    c.grab_mode = CAMERA_GRAB_LATEST;        // la foto debe ser del instante de la orden, no una vieja
    return esp_camera_init(&c) == ESP_OK;
}

// Promedio móvil separable (horizontal y luego vertical) sobre toda la imagen.
// [PENDIENTE] Difuminado SELECTIVO: detectar placas y rostros y difuminar solo esas zonas.
// Mientras no exista, se difumina TODO el cuadro: así ninguna placa ni rostro sale legible.
static void difuminar(uint8_t* img, int ancho, int alto, int r) {
    const int maxLado = ancho > alto ? ancho : alto;
    uint8_t* tmp = (uint8_t*)ps_malloc(maxLado);
    if (!tmp) return;
    for (int y = 0; y < alto; y++) {               // horizontal
        uint8_t* fila = img + y * ancho;
        for (int x = 0; x < ancho; x++) {
            int suma = 0, n = 0;
            for (int k = -r; k <= r; k++) {
                const int xx = x + k;
                if (xx >= 0 && xx < ancho) { suma += fila[xx]; n++; }
            }
            tmp[x] = suma / n;
        }
        memcpy(fila, tmp, ancho);
    }
    for (int x = 0; x < ancho; x++) {              // vertical
        for (int y = 0; y < alto; y++) {
            int suma = 0, n = 0;
            for (int k = -r; k <= r; k++) {
                const int yy = y + k;
                if (yy >= 0 && yy < alto) { suma += img[yy * ancho + x]; n++; }
            }
            tmp[y] = suma / n;
        }
        for (int y = 0; y < alto; y++) img[y * ancho + x] = tmp[y];
    }
    free(tmp);
}

static void tomarFoto(const String& id) {
    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
        Serial2.printf("ERR,%s,captura\n", id.c_str());
        return;
    }
    const uint32_t t0 = millis();
    difuminar(fb->buf, fb->width, fb->height, RADIO_DIFUMINADO);
    const uint32_t msDifuminado = millis() - t0;

    uint8_t* jpg = nullptr;
    size_t bytes = 0;
    const bool ok = frame2jpg(fb, 70, &jpg, &bytes);   // el original ya no existe: se difuminó en su lugar
    esp_camera_fb_return(fb);
    if (!ok) {
        Serial2.printf("ERR,%s,jpeg\n", id.c_str());
        return;
    }
    free(ultimaFoto);
    ultimaFoto = jpg;
    ultimaFotoBytes = bytes;
    // [PENDIENTE] enviar la miniatura al nodo (UART) o a la red; hoy solo queda en PSRAM.
    Serial2.printf("OK,%s,%u\n", id.c_str(), (unsigned)bytes);
    Serial.printf("[FOTO] id=%s %u bytes, difuminado %lu ms\n", id.c_str(), (unsigned)bytes, (unsigned long)msDifuminado);
}

void setup() {
    Serial.begin(115200);     // UART0 (GPIO 1/3): solo depuración
    pinMode(PIN_FLASH, OUTPUT);
    digitalWrite(PIN_FLASH, LOW);
    Serial2.begin(ENLACE_BAUD, SERIAL_8N1, PIN_ENLACE_RX, PIN_ENLACE_TX);
    Serial2.setTimeout(200);

    Serial.println("\n=== VÍA VIVA · nodo de cámara ===");
    Serial.printf("PSRAM: %u B\n", ESP.getPsramSize());   // [VALIDAR EN PLACA] ~4 MB
    const bool camOk = iniciarCamara();
    Serial.printf("[CAM] OV2640 %s\n", camOk ? "OK" : "NO INICIA");
    if (!camOk) {
        // Sigue respondiendo por UART para que el nodo sepa que la cámara falló
        for (;;) {
            if (Serial2.available()) {
                String linea = Serial2.readStringUntil('\n');
                linea.trim();
                if (linea == "PING") Serial2.print("ERR,0,camara\n");
                else if (linea.startsWith("FOTO,")) {
                    const int c2 = linea.indexOf(',', 5);
                    Serial2.printf("ERR,%s,camara\n", linea.substring(5, c2 < 0 ? linea.length() : c2).c_str());
                }
            }
            delay(5);
        }
    }
}

void loop() {
    if (!Serial2.available()) {
        delay(2);
        return;
    }
    String linea = Serial2.readStringUntil('\n');
    linea.trim();
    if (linea == "PING") {
        Serial2.print("PONG\n");
    } else if (linea.startsWith("FOTO,")) {
        const int c2 = linea.indexOf(',', 5);
        tomarFoto(linea.substring(5, c2 < 0 ? linea.length() : c2));
    } else if (linea.length()) {
        Serial2.print("ERR,0,orden_desconocida\n");
    }
}
