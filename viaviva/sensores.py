"""Controladores de los sensores conectados directo a la Raspberry Pi 4. [VALIDAR EN PLACA]: escrito sin la Pi.

Cada sensor es tolerante a fallos: si falta la librería, el módulo no responde o una lectura falla, queda en
`estado()` con su error y el resto sigue funcionando. Ninguno tumba la captura.

| Sensor   | Bus  | Librería (en la Pi)               | Cómo se lee                                                     |
|----------|------|-----------------------------------|-----------------------------------------------------------------|
| ADXL345  | SPI0 | spidev + gpiozero/lgpio           | FIFO stream, watermark 16 → INT1 → hilo que vacía la FIFO       |
| MPU-6050 | I2C1 | smbus2                            | Sondeo a 100 Hz (giro y aceleración, para maniobras)            |
| VL53L0X  | I2C1 | adafruit-circuitpython-vl53l0x    | Modo continuo, ~20 Hz (la inicialización de ST es larga)        |
| BH1750   | I2C1 | smbus2                            | Alta resolución continua, cada 1 s                              |
| NEO-6M   | UART | pyserial                          | NMEA RMC + GGA con verificación de suma (parser propio)         |
| DHT22    | GPIO | adafruit-circuitpython-dht        | Cada 10 s; los fallos de tiempo del protocolo son normales      |
"""
from __future__ import annotations

import math
import threading
import time
from datetime import datetime, timezone

from viaviva import config

G = 9.81


class Sensor:
    nombre = "sensor"

    def __init__(self):
        self.presente = False
        self.error: str | None = None
        self.lecturas = 0
        self.fallos = 0
        self.ultimo = None             # time.monotonic() de la última lectura buena

    def ok(self) -> None:
        self.lecturas += 1
        self.ultimo = time.monotonic()

    def falla(self, err) -> None:
        self.fallos += 1
        self.error = f"{type(err).__name__}: {err}"[:120]

    def estado(self) -> dict:
        edad = None if self.ultimo is None else round(time.monotonic() - self.ultimo, 1)
        return {"presente": self.presente, "lecturas": self.lecturas, "fallos": self.fallos, "edad_s": edad,
                "error": self.error}


# ------------------------------------------------------------------------------------------------ ADXL345 (SPI)
class ADXL345(Sensor):
    """FIFO + interrupción en GPIO como sustituto del DMA del ESP32: el ADXL345 junta 16 muestras en su FIFO,
    levanta INT1 y un hilo las lee todas de una vez. Linux no garantiza tiempo real, así que la FIFO (32 muestras
    = 160 ms a 200 Hz) es el colchón: si el hilo se atrasa > 160 ms, se pierden muestras y se cuenta en
    `desbordes` (bit OVERRUN de INT_SOURCE)."""
    nombre = "adxl345"
    R_DEVID, R_BW_RATE, R_POWER, R_INT_ENABLE, R_INT_MAP, R_INT_SOURCE = 0x00, 0x2C, 0x2D, 0x2E, 0x2F, 0x30
    R_DATA_FORMAT, R_DATAX0, R_FIFO_CTL, R_FIFO_STATUS = 0x31, 0x32, 0x38, 0x39
    LEER, MULTI = 0x80, 0x40
    ESCALA_G = 0.0039               # resolución completa: 3,9 mg/LSB en cualquier rango

    def __init__(self, fs: float = config.FS_ADXL_HZ, watermark: int = config.WATERMARK_FIFO,
                 cs: int = config.SPI_CS, con_interrupcion: bool = True):
        super().__init__()
        self.cs, self.con_interrupcion = cs, con_interrupcion
        if cs != config.SPI_CS:
            self.nombre = f"adxl345_{cs + 1}"
        self.fs, self.watermark = fs, watermark
        self.desbordes = 0
        self.spi = None
        self.int1 = None
        self.hay_datos = threading.Event()

    def _escribir(self, reg, val):
        self.spi.xfer2([reg & 0x3F, val])

    def _leer(self, reg, n=1):
        return self.spi.xfer2([reg | self.LEER | (self.MULTI if n > 1 else 0)] + [0] * n)[1:]

    def iniciar(self) -> bool:
        try:
            import spidev
            self.spi = spidev.SpiDev()
            self.spi.open(config.SPI_BUS, self.cs)
            self.spi.mode, self.spi.max_speed_hz = 3, config.SPI_HZ
            devid = self._leer(self.R_DEVID)[0]
            if devid != 0xE5:
                raise RuntimeError(f"DEVID 0x{devid:02X} (esperado 0xE5): revisar cableado SPI")
            self._escribir(self.R_POWER, 0x00)
            self._escribir(self.R_BW_RATE, {100: 0x0A, 200: 0x0B, 400: 0x0C}[int(self.fs)])
            self._escribir(self.R_DATA_FORMAT, 0x0B)                    # resolución completa, ±16 g
            self._escribir(self.R_FIFO_CTL, 0x80 | (self.watermark & 0x1F))   # modo stream + watermark
            self._escribir(self.R_INT_MAP, 0x00)                        # todo a INT1
            self._escribir(self.R_INT_ENABLE, 0x02)                     # watermark
            self._escribir(self.R_POWER, 0x08)                          # medir
            try:
                if not self.con_interrupcion:
                    raise RuntimeError("sin INT1 (se lee junto con el #1)")
                from gpiozero import DigitalInputDevice
                self.int1 = DigitalInputDevice(config.PIN_INT1, pull_up=None, active_state=True)
                self.int1.when_activated = self.hay_datos.set
            except Exception as err:                                    # sin interrupción: sondeo cada 50 ms
                self.error = f"INT1 no disponible ({err}); se sondea la FIFO"
            self.presente = True
        except Exception as err:
            self.falla(err)
        return self.presente

    def leer_fifo(self) -> list[tuple[float, float, float]]:
        """Vacía la FIFO: una transacción de 7 bytes por muestra (con CS alto entre ellas la FIFO avanza)."""
        if self._leer(self.R_INT_SOURCE)[0] & 0x01:
            self.desbordes += 1
        n = self._leer(self.R_FIFO_STATUS)[0] & 0x3F
        muestras = []
        for _ in range(n):
            b = self._leer(self.R_DATAX0, 6)
            x, y, z = (int.from_bytes(bytes(b[i:i + 2]), "little", signed=True) for i in (0, 2, 4))
            muestras.append((x * self.ESCALA_G * G, y * self.ESCALA_G * G, z * self.ESCALA_G * G))
        if muestras:
            self.ok()
        return muestras

    def estado(self) -> dict:
        return {**super().estado(), "desbordes_fifo": self.desbordes, "interrupcion": self.int1 is not None}


# ------------------------------------------------------------------------------------------------ I2C
class _I2C(Sensor):
    direccion = 0x00

    def __init__(self, bus):
        super().__init__()
        self.bus = bus


class MPU6050(_I2C):
    nombre, direccion = "mpu6050", 0x68
    ESCALA_ACC = 8192.0             # ±4 g
    ESCALA_GIRO = 65.5              # ±500 °/s

    def iniciar(self) -> bool:
        try:
            if self.bus.read_byte_data(self.direccion, 0x75) not in (0x68, 0x70, 0x72):
                raise RuntimeError("WHO_AM_I inesperado")
            self.bus.write_byte_data(self.direccion, 0x6B, 0x01)     # despertar, reloj del giro X
            self.bus.write_byte_data(self.direccion, 0x1A, 0x03)     # filtro digital ~44 Hz
            self.bus.write_byte_data(self.direccion, 0x1B, 0x08)     # ±500 °/s
            self.bus.write_byte_data(self.direccion, 0x1C, 0x08)     # ±4 g
            self.presente = True
        except Exception as err:
            self.falla(err)
        return self.presente

    def leer(self):
        """→ (ax, ay, az) m/s², (gx, gy, gz) rad/s."""
        b = self.bus.read_i2c_block_data(self.direccion, 0x3B, 14)
        v = [int.from_bytes(bytes(b[i:i + 2]), "big", signed=True) for i in range(0, 14, 2)]
        self.ok()
        acc = tuple(x / self.ESCALA_ACC * G for x in v[0:3])
        giro = tuple(math.radians(x / self.ESCALA_GIRO) for x in v[4:7])
        return acc, giro


class BH1750(_I2C):
    nombre, direccion = "bh1750", 0x23

    def iniciar(self) -> bool:
        try:
            self.bus.write_byte(self.direccion, 0x01)                 # encender
            self.bus.write_byte(self.direccion, 0x10)                 # alta resolución continua (120 ms)
            self.presente = True
        except Exception as err:
            self.falla(err)
        return self.presente

    def leer(self) -> float:
        from smbus2 import i2c_msg
        m = i2c_msg.read(self.direccion, 2)
        self.bus.i2c_rdwr(m)
        b = list(m)
        self.ok()
        return (b[0] << 8 | b[1]) / 1.2


class VL53L0X(Sensor):
    nombre = "vl53l0x"

    def __init__(self):
        super().__init__()
        self.dev = None

    def iniciar(self) -> bool:
        try:
            import board
            import busio
            import adafruit_vl53l0x
            self.dev = adafruit_vl53l0x.VL53L0X(busio.I2C(board.SCL, board.SDA))
            self.dev.measurement_timing_budget = 33000
            self.dev.start_continuous()
            self.presente = True
        except Exception as err:
            self.falla(err)
        return self.presente

    def leer(self) -> float | None:
        if not self.dev.data_ready:
            return None
        mm = float(self.dev.range)
        self.ok()
        return mm if mm < 8000 else math.nan                          # 8190 = fuera de rango


class DHT22(Sensor):
    """El protocolo de un hilo depende de tiempos de µs que Linux no garantiza: fallar 1 de cada 3 es normal.
    Se reintenta en la siguiente vuelta y se informa la edad del último dato bueno."""
    nombre = "dht22"

    def __init__(self):
        super().__init__()
        self.dev = None

    def iniciar(self) -> bool:
        try:
            import board
            import adafruit_dht
            self.dev = adafruit_dht.DHT22(getattr(board, f"D{config.PIN_DHT22}"), use_pulseio=False)
            self.presente = True
        except Exception as err:
            self.falla(err)
        return self.presente

    def leer(self):
        try:
            t, h = self.dev.temperature, self.dev.humidity
            if t is None or h is None or not (-40 <= t <= 80 and 0 <= h <= 100):
                raise RuntimeError("lectura fuera de rango")
            self.ok()
            return t, h
        except Exception as err:
            self.falla(err)
            return None


# ------------------------------------------------------------------------------------------------ GPS (NMEA)
def suma_nmea_ok(linea: str) -> bool:
    if not linea.startswith("$") or "*" not in linea:
        return False
    cuerpo, suma = linea[1:].split("*", 1)
    x = 0
    for c in cuerpo:
        x ^= ord(c)
    try:
        return x == int(suma[:2], 16)
    except ValueError:
        return False


def _grados(valor: str, hemisferio: str) -> float:
    if not valor:
        return math.nan
    punto = valor.index(".")
    g = float(valor[:punto - 2]) + float(valor[punto - 2:]) / 60.0
    return -g if hemisferio in ("S", "W") else g


class ParserNMEA:
    """RMC (hora, fecha, posición, velocidad, rumbo, válido) + GGA (calidad, satélites, HDOP, altura).
    Devuelve un fix en cada RMC (1 Hz en el NEO-6M)."""

    def __init__(self):
        self.gga = {"sat": 0, "hdop": math.nan, "alt": math.nan, "calidad": 0}

    def linea(self, linea: str) -> dict | None:
        linea = linea.strip()
        if not suma_nmea_ok(linea):
            return None
        c = linea[1:linea.index("*")].split(",")
        tipo = c[0][2:]
        if tipo == "GGA" and len(c) >= 10:
            self.gga = {"calidad": int(c[6] or 0), "sat": int(c[7] or 0),
                        "hdop": float(c[8]) if c[8] else math.nan, "alt": float(c[9]) if c[9] else math.nan}
            return None
        if tipo != "RMC" or len(c) < 10:
            return None
        valido = c[2] == "A"
        utc = None
        if c[1] and c[9]:
            hh, mm, ss = int(c[1][0:2]), int(c[1][2:4]), float(c[1][4:])
            d, mo, a = int(c[9][0:2]), int(c[9][2:4]), 2000 + int(c[9][4:6])
            utc = datetime(a, mo, d, hh, mm, int(ss), int(round((ss % 1) * 1e6)) % 1000000,
                           tzinfo=timezone.utc).timestamp()
        nudos = float(c[7]) if c[7] else math.nan
        return {"valido": valido, "utc_epoch": utc,
                "lat": _grados(c[3], c[4]) if valido else math.nan, "lon": _grados(c[5], c[6]) if valido else math.nan,
                "vel_ms": nudos * 0.514444 if valido else math.nan, "rumbo": float(c[8]) if c[8] else math.nan,
                # precisión aproximada = HDOP × 2,5 m (error típico del NEO-6M con HDOP 1); es una estimación
                "precision_m": self.gga["hdop"] * 2.5 if valido else math.nan,
                "alt": self.gga["alt"], "sat": self.gga["sat"]}


class GPS(Sensor):
    nombre = "gps_neo6m"

    def __init__(self):
        super().__init__()
        self.puerto = None
        self.parser = ParserNMEA()
        self.fix = False

    def iniciar(self) -> bool:
        try:
            import serial
            self.puerto = serial.Serial(config.UART_GPS, config.GPS_BAUD, timeout=1.0)
            self.presente = True
        except Exception as err:
            self.falla(err)
        return self.presente

    def leer_linea(self) -> dict | None:
        b = self.puerto.readline()
        if not b:
            raise TimeoutError("el GPS no envía datos (revisar TX del GPS → GPIO 15)")
        r = self.parser.linea(b.decode("ascii", "replace"))
        if r is not None:
            self.ok()
            self.fix = r["valido"]
        return r

    def estado(self) -> dict:
        return {**super().estado(), "fix": self.fix, "satelites": self.parser.gga["sat"]}
