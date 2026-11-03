// Controladores mínimos (a nivel de registros) de los sensores de ambiente del nodo:
//   BME280  (I2C 0x76 o 0x77): temperatura, humedad y presión. Si el chip es un BMP280 (ID 0x58) no mide humedad.
//   BH1750  (I2C 0x23 con ADDR a GND; 0x5C con ADDR en alto): luz en lux.
//   DHT22   (un hilo en PIN_DHT22): temperatura y humedad, plan B si no hay BME280.
// Está en include/ (no en src/) para que los programas de pruebas/ usen exactamente el mismo código.
// Las fórmulas de compensación del BME280 son las enteras de la hoja de datos de Bosch (sección 4.2.3).
#pragma once
#include <Arduino.h>
#include <Wire.h>

class BME280 {
public:
    static constexpr uint8_t ID_BME280 = 0x60;
    static constexpr uint8_t ID_BMP280 = 0x58;

    // Busca el sensor en 0x76 y 0x77. Devuelve true si hay un BME280 o un BMP280.
    bool iniciar(TwoWire& bus) {
        bus_ = &bus;
        for (uint8_t dir : {(uint8_t)0x76, (uint8_t)0x77}) {
            dir_ = dir;
            id_ = leer8(0xD0);
            if (id_ == ID_BME280 || id_ == ID_BMP280) break;
            id_ = 0;
        }
        if (!id_) return false;
        escribir(0xE0, 0xB6);   // reinicio por software
        delay(5);
        for (int i = 0; i < 20 && (leer8(0xF3) & 0x01); i++) delay(2);   // espera a que copie la calibración
        if (!leerCalibracion()) return false;
        // Modo normal: sobremuestreo ×1 en T, P y H; reposo 1 s entre medidas; sin filtro IIR.
        // ctrl_hum (0xF2) solo surte efecto después de escribir ctrl_meas (0xF4).
        if (tieneHumedad()) escribir(0xF2, 0x01);
        escribir(0xF5, 0xA0);
        escribir(0xF4, 0x27);
        return true;
    }

    // Lee la última medida. humedad = NAN si el chip es BMP280.
    bool leer(float& tempC, float& humPct, float& presHpa) {
        uint8_t b[8];
        const uint8_t n = tieneHumedad() ? 8 : 6;
        if (!leerBloque(0xF7, b, n)) return false;
        const int32_t adcP = ((int32_t)b[0] << 12) | ((int32_t)b[1] << 4) | (b[2] >> 4);
        const int32_t adcT = ((int32_t)b[3] << 12) | ((int32_t)b[4] << 4) | (b[5] >> 4);
        if (adcT == 0x80000) return false;   // valor de "sin medida" (todavía no ha medido)
        tempC = compensarT(adcT) / 100.0f;
        presHpa = compensarP(adcP) / 256.0f / 100.0f;
        humPct = NAN;
        if (n == 8) {
            const int32_t adcH = ((int32_t)b[6] << 8) | b[7];
            humPct = compensarH(adcH) / 1024.0f;
        }
        return true;
    }

    bool tieneHumedad() const { return id_ == ID_BME280; }
    uint8_t chipId() const { return id_; }
    uint8_t direccion() const { return dir_; }

    // Públicas para poder probar la compensación con el ejemplo de la hoja de datos.
    uint16_t T1 = 0, P1 = 0;
    int16_t T2 = 0, T3 = 0, P2 = 0, P3 = 0, P4 = 0, P5 = 0, P6 = 0, P7 = 0, P8 = 0, P9 = 0;
    uint8_t H1 = 0, H3 = 0;
    int16_t H2 = 0, H4 = 0, H5 = 0;
    int8_t H6 = 0;

    int32_t compensarT(int32_t adcT) {   // centésimas de °C; actualiza tFino_
        const int32_t v1 = ((((adcT >> 3) - ((int32_t)T1 << 1))) * ((int32_t)T2)) >> 11;
        const int32_t v2 = (((((adcT >> 4) - ((int32_t)T1)) * ((adcT >> 4) - ((int32_t)T1))) >> 12) * ((int32_t)T3)) >> 14;
        tFino_ = v1 + v2;
        return (tFino_ * 5 + 128) >> 8;
    }

    uint32_t compensarP(int32_t adcP) const {   // Pa × 256 (Q24.8)
        int64_t v1 = (int64_t)tFino_ - 128000;
        int64_t v2 = v1 * v1 * (int64_t)P6;
        v2 = v2 + ((v1 * (int64_t)P5) << 17);
        v2 = v2 + (((int64_t)P4) << 35);
        v1 = ((v1 * v1 * (int64_t)P3) >> 8) + ((v1 * (int64_t)P2) << 12);
        v1 = ((((int64_t)1) << 47) + v1) * ((int64_t)P1) >> 33;
        if (v1 == 0) return 0;   // evita dividir por cero
        int64_t p = 1048576 - adcP;
        p = (((p << 31) - v2) * 3125) / v1;
        v1 = (((int64_t)P9) * (p >> 13) * (p >> 13)) >> 25;
        v2 = (((int64_t)P8) * p) >> 19;
        p = ((p + v1 + v2) >> 8) + (((int64_t)P7) << 4);
        return (uint32_t)p;
    }

    uint32_t compensarH(int32_t adcH) const {   // %HR × 1024 (Q22.10)
        int32_t v = tFino_ - (int32_t)76800;
        v = (((((adcH << 14) - (((int32_t)H4) << 20) - (((int32_t)H5) * v)) + ((int32_t)16384)) >> 15) *
             (((((((v * ((int32_t)H6)) >> 10) * (((v * ((int32_t)H3)) >> 11) + ((int32_t)32768))) >> 10) +
                ((int32_t)2097152)) * ((int32_t)H2) + 8192) >> 14));
        v = v - (((((v >> 15) * (v >> 15)) >> 7) * ((int32_t)H1)) >> 4);
        v = v < 0 ? 0 : v;
        v = v > 419430400 ? 419430400 : v;
        return (uint32_t)(v >> 12);
    }

private:
    bool leerCalibracion() {
        uint8_t c[26];
        if (!leerBloque(0x88, c, 26)) return false;
        auto u16 = [&](int i) { return (uint16_t)(c[i] | (c[i + 1] << 8)); };   // little-endian
        T1 = u16(0);  T2 = (int16_t)u16(2);  T3 = (int16_t)u16(4);
        P1 = u16(6);  P2 = (int16_t)u16(8);  P3 = (int16_t)u16(10); P4 = (int16_t)u16(12);
        P5 = (int16_t)u16(14); P6 = (int16_t)u16(16); P7 = (int16_t)u16(18);
        P8 = (int16_t)u16(20); P9 = (int16_t)u16(22);
        if (!tieneHumedad()) return true;
        H1 = c[25];   // 0xA1
        uint8_t h[7];
        if (!leerBloque(0xE1, h, 7)) return false;
        H2 = (int16_t)(h[0] | (h[1] << 8));
        H3 = h[2];
        H4 = (int16_t)(((int8_t)h[3] << 4) | (h[4] & 0x0F));
        H5 = (int16_t)(((int8_t)h[5] << 4) | (h[4] >> 4));
        H6 = (int8_t)h[6];
        return true;
    }

    uint8_t leer8(uint8_t reg) {
        uint8_t v = 0xFF;
        return leerBloque(reg, &v, 1) ? v : 0xFF;
    }
    bool leerBloque(uint8_t reg, uint8_t* b, uint8_t n) {
        bus_->beginTransmission(dir_);
        bus_->write(reg);
        if (bus_->endTransmission(false) != 0) return false;
        if (bus_->requestFrom(dir_, n) != n) return false;
        for (int i = 0; i < n; i++) b[i] = bus_->read();
        return true;
    }
    void escribir(uint8_t reg, uint8_t valor) {
        bus_->beginTransmission(dir_);
        bus_->write(reg);
        bus_->write(valor);
        bus_->endTransmission();
    }

    TwoWire* bus_ = nullptr;
    uint8_t dir_ = 0x76, id_ = 0;
    int32_t tFino_ = 0;
};

class BH1750 {
public:
    // Encendido + modo continuo de alta resolución (1 lx, 120 ms típico por medida).
    bool iniciar(TwoWire& bus, uint8_t direccion = 0x23) {
        bus_ = &bus;
        dir_ = direccion;
        if (!comando(0x01)) return false;   // POWER_ON
        return comando(0x10);               // CONT_H_RES_MODE
    }

    bool leer(float& lux) {
        if (bus_->requestFrom(dir_, (uint8_t)2) != 2) return false;
        const uint16_t crudo = (bus_->read() << 8) | bus_->read();
        lux = crudo / 1.2f;   // hoja de datos: lx = cuenta / 1,2 con MTreg por defecto
        return true;
    }

    uint8_t direccion() const { return dir_; }

private:
    bool comando(uint8_t c) {
        bus_->beginTransmission(dir_);
        bus_->write(c);
        return bus_->endTransmission() == 0;
    }
    TwoWire* bus_ = nullptr;
    uint8_t dir_ = 0x23;
};

// DHT22 (AM2302): protocolo de un hilo propio. La lectura dura ~5 ms con las interrupciones del núcleo
// apagadas (los tiempos de bit son de 26-70 µs). Mínimo 2 s entre lecturas. Necesita pull-up de 10 kΩ a 3V3
// (los módulos de 3 pines ya la traen).
class DHT22 {
public:
    enum Error : uint8_t { OK = 0, SIN_RESPUESTA, TIEMPO_BIT, SUMA };

    void iniciar(int pin) {
        pin_ = pin;
        pinMode(pin_, INPUT_PULLUP);
    }

    Error leer(float& tempC, float& humPct) {
        uint8_t d[5] = {0};
        pinMode(pin_, OUTPUT);
        digitalWrite(pin_, LOW);
        delayMicroseconds(1100);   // inicio: ≥ 1 ms en bajo
        Error e = OK;
        portENTER_CRITICAL(&mux_);
        pinMode(pin_, INPUT_PULLUP);
        delayMicroseconds(30);
        // Respuesta del sensor: ~80 µs en bajo y ~80 µs en alto
        if (esperar(LOW, 100) < 0 || esperar(HIGH, 100) < 0) e = SIN_RESPUESTA;
        for (int i = 0; e == OK && i < 40; i++) {
            if (esperar(LOW, 80) < 0) { e = TIEMPO_BIT; break; }     // 50 µs en bajo antes de cada bit
            const int alto = esperar(HIGH, 100);                    // 26-28 µs = 0, ~70 µs = 1
            if (alto < 0) { e = TIEMPO_BIT; break; }
            d[i / 8] = (d[i / 8] << 1) | (alto > 40 ? 1 : 0);
        }
        portEXIT_CRITICAL(&mux_);
        if (e != OK) return e;
        if ((uint8_t)(d[0] + d[1] + d[2] + d[3]) != d[4]) return SUMA;
        humPct = ((d[0] << 8) | d[1]) / 10.0f;
        const int16_t t = ((d[2] & 0x7F) << 8) | d[3];
        tempC = (d[2] & 0x80 ? -t : t) / 10.0f;
        return OK;
    }

    static const char* nombreError(Error e) {
        switch (e) {
            case OK: return "ok";
            case SIN_RESPUESTA: return "sin respuesta";
            case TIEMPO_BIT: return "tiempo de bit";
            default: return "suma de verificación";
        }
    }

private:
    // Espera mientras el pin esté en 'nivel'; devuelve cuánto duró (µs) o -1 si pasó el tiempo máximo.
    int esperar(int nivel, int maxUs) {
        const uint32_t t0 = micros();
        while (digitalRead(pin_) == nivel) {
            if ((int)(micros() - t0) > maxUs) return -1;
        }
        return (int)(micros() - t0);
    }
    int pin_ = -1;
    portMUX_TYPE mux_ = portMUX_INITIALIZER_UNLOCKED;
};
