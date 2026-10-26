// Controlador mínimo del MPU-6050 por I2C (a nivel de registros).
// Sirve como giroscopio y como línea base del experimento E4 (I2C vs. SPI).
#pragma once
#include <Arduino.h>
#include <Wire.h>

struct LecturaMPU {
    float ax, ay, az;   // g
    float gx, gy, gz;   // °/s
};

class MPU6050 {
public:
    static constexpr uint8_t DIRECCION = 0x68;

    bool iniciar(TwoWire& bus) {
        bus_ = &bus;
        if (leer(0x75) != 0x68) return false;   // WHO_AM_I
        escribir(0x6B, 0x01);   // PWR_MGMT_1: sale de reposo, reloj del giroscopio X
        escribir(0x1A, 0x03);   // CONFIG: filtro pasa-bajos digital ~44 Hz
        escribir(0x1B, 0x08);   // GYRO_CONFIG: ±500 °/s
        escribir(0x1C, 0x10);   // ACCEL_CONFIG: ±8 g
        return true;
    }

    bool leerTodo(LecturaMPU& l) {
        uint8_t b[14];
        bus_->beginTransmission(DIRECCION);
        bus_->write(0x3B);                       // ACCEL_XOUT_H
        if (bus_->endTransmission(false) != 0) return false;
        if (bus_->requestFrom(DIRECCION, (uint8_t)14) != 14) return false;
        for (int i = 0; i < 14; i++) b[i] = bus_->read();
        auto v = [&](int i) { return (int16_t)((b[i] << 8) | b[i + 1]); };
        l.ax = v(0) / 4096.0f;   // ±8 g → 4096 LSB/g
        l.ay = v(2) / 4096.0f;
        l.az = v(4) / 4096.0f;
        l.gx = v(8) / 65.5f;     // ±500 °/s → 65,5 LSB/(°/s)
        l.gy = v(10) / 65.5f;
        l.gz = v(12) / 65.5f;
        return true;
    }

private:
    uint8_t leer(uint8_t reg) {
        bus_->beginTransmission(DIRECCION);
        bus_->write(reg);
        if (bus_->endTransmission(false) != 0) return 0xFF;
        if (bus_->requestFrom(DIRECCION, (uint8_t)1) != 1) return 0xFF;
        return bus_->read();
    }
    void escribir(uint8_t reg, uint8_t valor) {
        bus_->beginTransmission(DIRECCION);
        bus_->write(reg);
        bus_->write(valor);
        bus_->endTransmission();
    }

    TwoWire* bus_ = nullptr;
};
