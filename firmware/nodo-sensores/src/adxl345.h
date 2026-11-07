// Controlador propio del ADXL345 por SPI con el driver spi_master de ESP-IDF.
// Se escribe a nivel de registros (sin librería) para controlar la FIFO, la interrupción
// y las transferencias por DMA, que son lo que mide el experimento E1.
#pragma once
#include <Arduino.h>
#include "driver/spi_master.h"

struct MuestraAcc {
    int16_t x, y, z;   // cuentas crudas; en resolución completa 1 LSB ≈ 3,9 mg
};

class ADXL345 {
public:
    static constexpr float G_POR_LSB = 0.0039f;
    static constexpr uint8_t DEVID_ESPERADO = 0xE5;

    // Registros usados (hoja de datos ADXL345, tabla 19)
    static constexpr uint8_t REG_DEVID       = 0x00;
    static constexpr uint8_t REG_BW_RATE     = 0x2C;
    static constexpr uint8_t REG_POWER_CTL   = 0x2D;
    static constexpr uint8_t REG_INT_ENABLE  = 0x2E;
    static constexpr uint8_t REG_INT_MAP     = 0x2F;
    static constexpr uint8_t REG_INT_SOURCE  = 0x30;
    static constexpr uint8_t REG_DATA_FORMAT = 0x31;
    static constexpr uint8_t REG_DATAX0      = 0x32;
    static constexpr uint8_t REG_FIFO_CTL    = 0x38;
    static constexpr uint8_t REG_FIFO_STATUS = 0x39;

    static constexpr uint8_t INT_DATA_READY = 0x80;
    static constexpr uint8_t INT_WATERMARK  = 0x02;
    static constexpr uint8_t INT_OVERRUN    = 0x01;

    // Inicia el bus VSPI (SPI3_HOST) con DMA y registra el dispositivo. Devuelve false si no responde.
    bool iniciar(int pinSck, int pinMosi, int pinMiso, int pinCs, int hzSpi);

    // modo: 0 polling, 1 DATA_READY por muestra, 2 FIFO en modo stream con watermark
    bool configurar(uint16_t fsHz, uint8_t modo, uint8_t watermark);

    uint8_t leerRegistro(uint8_t reg);
    void escribirRegistro(uint8_t reg, uint8_t valor);

    MuestraAcc leerMuestra();                     // una muestra, transacción por sondeo
    uint8_t muestrasEnFifo();                     // FIFO_STATUS & 0x3F (0..32)
    uint8_t fuenteInterrupcion();                 // INT_SOURCE

    // Encola n lecturas de 6 bytes por DMA y espera el resultado.
    // Mientras el DMA trabaja la tarea queda bloqueada y la CPU queda libre.
    bool leerLoteDMA(MuestraAcc* destino, uint8_t n);

    uint8_t devid() const { return devid_; }

private:
    static constexpr int MAX_LOTE = 33;   // 32 de la FIFO + 1 en los registros de salida
    // DMA en ESP32 exige buffers alineados a 32 bits y transferencias múltiplo de 4 bytes.
    // ADXL345 necesita 1 byte de comando + 6 de datos; se rellena a 8 bytes por transacción.
    static constexpr int BYTES_DMA = 8;

    static uint8_t codigoTasa(uint16_t fsHz);

    spi_device_handle_t dev_ = nullptr;
    spi_transaction_t trans_[MAX_LOTE];
    uint8_t* tx_ = nullptr;   // búferes en memoria apta para DMA
    uint8_t* rx_ = nullptr;
    uint8_t devid_ = 0;
};
