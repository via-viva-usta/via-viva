#include "adxl345.h"

#include <string.h>
#include "esp_heap_caps.h"

// Bits del primer byte SPI: R/W (bit 7) y multibyte (bit 6)
static constexpr uint8_t SPI_LEER = 0x80;
static constexpr uint8_t SPI_MULTIBYTE = 0x40;

// VSPI (SPI3_HOST) en la ESP32 normal; el HSPI (SPI2_HOST) queda para la microSD
static constexpr spi_host_device_t HOST_SPI = SPI3_HOST;

bool ADXL345::iniciar(int pinSck, int pinMosi, int pinMiso, int pinCs, int hzSpi) {
    spi_bus_config_t bus;
    memset(&bus, 0, sizeof(bus));
    bus.mosi_io_num = pinMosi;
    bus.miso_io_num = pinMiso;
    bus.sclk_io_num = pinSck;
    bus.quadwp_io_num = -1;
    bus.quadhd_io_num = -1;
    bus.max_transfer_sz = BYTES_DMA;
    if (spi_bus_initialize(HOST_SPI, &bus, SPI_DMA_CH_AUTO) != ESP_OK) return false;

    spi_device_interface_config_t cfg;
    memset(&cfg, 0, sizeof(cfg));
    cfg.mode = 3;                    // CPOL = 1, CPHA = 1 (hoja de datos)
    cfg.clock_speed_hz = hzSpi;
    cfg.spics_io_num = pinCs;
    cfg.queue_size = MAX_LOTE;       // permite encolar un lote completo de lecturas
    if (spi_bus_add_device(HOST_SPI, &cfg, &dev_) != ESP_OK) return false;

    tx_ = (uint8_t*)heap_caps_calloc(MAX_LOTE, BYTES_DMA, MALLOC_CAP_DMA);
    rx_ = (uint8_t*)heap_caps_calloc(MAX_LOTE, BYTES_DMA, MALLOC_CAP_DMA);
    if (!tx_ || !rx_) return false;
    for (int i = 0; i < MAX_LOTE; i++) {
        tx_[i * BYTES_DMA] = REG_DATAX0 | SPI_LEER | SPI_MULTIBYTE;
    }

    devid_ = leerRegistro(REG_DEVID);
    return devid_ == DEVID_ESPERADO;
}

uint8_t ADXL345::codigoTasa(uint16_t fsHz) {
    // BW_RATE: 0x0A = 100 Hz, 0x0B = 200 Hz, 0x0C = 400 Hz, 0x0D = 800 Hz, 0x0E = 1600 Hz, 0x0F = 3200 Hz
    if (fsHz >= 3200) return 0x0F;
    if (fsHz >= 1600) return 0x0E;
    if (fsHz >= 800) return 0x0D;
    if (fsHz >= 400) return 0x0C;
    if (fsHz >= 200) return 0x0B;
    return 0x0A;
}

bool ADXL345::configurar(uint16_t fsHz, uint8_t modo, uint8_t watermark) {
    escribirRegistro(REG_POWER_CTL, 0x00);          // standby mientras se configura
    escribirRegistro(REG_BW_RATE, codigoTasa(fsHz));
    escribirRegistro(REG_DATA_FORMAT, 0x0B);        // FULL_RES, ±16 g, INT activa en alto, SPI 4 hilos
    escribirRegistro(REG_INT_MAP, 0x00);            // todas las interrupciones a INT1

    if (modo == 2) {
        // FIFO en modo stream (bits 7:6 = 10) con watermark (bits 4:0)
        escribirRegistro(REG_FIFO_CTL, 0x80 | (watermark & 0x1F));
        escribirRegistro(REG_INT_ENABLE, INT_WATERMARK | INT_OVERRUN);
    } else {
        escribirRegistro(REG_FIFO_CTL, 0x00);       // bypass
        escribirRegistro(REG_INT_ENABLE, modo == 1 ? INT_DATA_READY : 0x00);
    }
    escribirRegistro(REG_POWER_CTL, 0x08);          // modo medición

    // Comprobación de lectura de vuelta (detecta clones GY-291 que no responden bien por SPI)
    return leerRegistro(REG_DATA_FORMAT) == 0x0B && leerRegistro(REG_BW_RATE) == codigoTasa(fsHz);
}

uint8_t ADXL345::leerRegistro(uint8_t reg) {
    spi_transaction_t t;
    memset(&t, 0, sizeof(t));
    t.flags = SPI_TRANS_USE_TXDATA | SPI_TRANS_USE_RXDATA;
    t.length = 16;
    t.tx_data[0] = reg | SPI_LEER;
    spi_device_polling_transmit(dev_, &t);
    return t.rx_data[1];
}

void ADXL345::escribirRegistro(uint8_t reg, uint8_t valor) {
    spi_transaction_t t;
    memset(&t, 0, sizeof(t));
    t.flags = SPI_TRANS_USE_TXDATA;
    t.length = 16;
    t.tx_data[0] = reg & 0x3F;
    t.tx_data[1] = valor;
    spi_device_polling_transmit(dev_, &t);
}

static inline MuestraAcc decodificar(const uint8_t* b) {
    // b[0] es el eco de la dirección; datos en little endian
    MuestraAcc m;
    m.x = (int16_t)(b[1] | (b[2] << 8));
    m.y = (int16_t)(b[3] | (b[4] << 8));
    m.z = (int16_t)(b[5] | (b[6] << 8));
    return m;
}

MuestraAcc ADXL345::leerMuestra() {
    spi_transaction_t t;
    memset(&t, 0, sizeof(t));
    t.length = BYTES_DMA * 8;
    t.tx_buffer = tx_;
    t.rx_buffer = rx_;
    spi_device_polling_transmit(dev_, &t);
    return decodificar(rx_);
}

uint8_t ADXL345::muestrasEnFifo() { return leerRegistro(REG_FIFO_STATUS) & 0x3F; }

uint8_t ADXL345::fuenteInterrupcion() { return leerRegistro(REG_INT_SOURCE); }

bool ADXL345::leerLoteDMA(MuestraAcc* destino, uint8_t n) {
    if (n == 0) return true;
    if (n > MAX_LOTE) n = MAX_LOTE;
    uint8_t encoladas = 0;
    // Cada lectura de 6 bytes saca una entrada de la FIFO; el CS sube entre transacciones.
    for (uint8_t i = 0; i < n; i++) {
        spi_transaction_t& t = trans_[i];
        memset(&t, 0, sizeof(t));
        // El stride y la longitud son múltiplos de 4: cada buffer queda alineado para DMA.
        t.length = BYTES_DMA * 8;
        t.tx_buffer = tx_ + i * BYTES_DMA;
        t.rx_buffer = rx_ + i * BYTES_DMA;
        if (spi_device_queue_trans(dev_, &t, portMAX_DELAY) != ESP_OK) {
            // No dejar transacciones previas pendientes si el driver rechaza una del lote.
            for (uint8_t j = 0; j < encoladas; j++) {
                spi_transaction_t* hecha = nullptr;
                spi_device_get_trans_result(dev_, &hecha, portMAX_DELAY);
            }
            return false;
        }
        encoladas++;
    }
    bool ok = true;
    for (uint8_t i = 0; i < n; i++) {
        spi_transaction_t* hecha = nullptr;
        if (spi_device_get_trans_result(dev_, &hecha, portMAX_DELAY) != ESP_OK) ok = false;
    }
    if (!ok) return false;
    for (uint8_t i = 0; i < n; i++) destino[i] = decodificar(rx_ + i * BYTES_DMA);
    return true;
}
