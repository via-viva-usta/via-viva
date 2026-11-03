// Prueba de la microSD por HSPI enrutado por la matriz GPIO (SCK 14, MISO 27, MOSI 13, CS 32).
// La tarjeta debe estar en FAT32 (las de 64 GB o más vienen en exFAT: formatearlas en FAT32 o usar una de ≤ 32 GB).
#include <SD.h>
#include <SPI.h>

#include "pines.h"
#include "resultado.h"

static SPIClass hspi(HSPI);

void setup() {
    encabezado("microSD (HSPI)");
    hspi.begin(PIN_SD_SCK, PIN_SD_MISO, PIN_SD_MOSI, PIN_SD_CS);
    const bool ok = SD.begin(PIN_SD_CS, hspi, 10000000);
    verificar(ok, "monta la tarjeta a 10 MHz",
              "revisar cables (SCK 14, MISO 27, MOSI 13, CS 32), 5 V si el módulo tiene regulador, y que esté en FAT32");
    if (ok) {
        const uint8_t tipo = SD.cardType();
        Serial.printf("  tipo: %s · tamaño: %llu MB · usado: %llu MB\n",
                      tipo == CARD_SDHC ? "SDHC" : tipo == CARD_SD ? "SD" : tipo == CARD_MMC ? "MMC" : "desconocido",
                      SD.cardSize() / (1024 * 1024), SD.usedBytes() / (1024 * 1024));
        // Escritura de 256 KB en bloques de 512 B (como el registro crudo) y relectura
        File f = SD.open("/prueba_sd.bin", FILE_WRITE);
        uint8_t bloque[512];
        for (int i = 0; i < 512; i++) bloque[i] = i & 0xFF;
        const uint32_t t0 = micros();
        size_t escritos = 0;
        for (int i = 0; f && i < 512; i++) escritos += f.write(bloque, sizeof(bloque));
        if (f) f.close();
        const float seg = (micros() - t0) / 1e6f;
        const float kbps = escritos / 1024.0f / seg;
        Serial.printf("  escritura: %u bytes en %.2f s = %.0f KB/s (el registro crudo necesita ~5 KB/s)\n",
                      (unsigned)escritos, seg, kbps);
        verificar(escritos == 512 * 512, "escribe 256 KB completos");
        verificar(kbps > 50, "velocidad de escritura > 50 KB/s", "tarjeta lenta o cables largos: bajar a 4 MHz");
        f = SD.open("/prueba_sd.bin", FILE_READ);
        bool iguales = f && f.size() == escritos;
        for (int i = 0; iguales && i < 512; i++) {
            uint8_t leido[512];
            iguales = f.read(leido, 512) == 512 && memcmp(leido, bloque, 512) == 0;
        }
        if (f) f.close();
        verificar(iguales, "relee exactamente lo escrito");
        SD.remove("/prueba_sd.bin");
    }
    resultadoFinal("microSD");
}

void loop() {}
