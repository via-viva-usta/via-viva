"""Fase C sin Raspberry: los controladores de la Pi con spidev, pyserial y gpiozero FALSOS (sin probar en hardware).
Comprueba que la captura arranca aunque falten sensores, lee la FIFO del ADXL #1 y #2, el GPS por NMEA y lo informa."""
import sys
import time
import types

import pytest


def _nmea(cuerpo: str) -> bytes:
    x = 0
    for c in cuerpo:
        x ^= ord(c)
    return f"${cuerpo}*{x:02X}\r\n".encode()


class SpiFalso:
    """ADXL345 que siempre tiene 16 muestras de 1 g en z (256 cuentas a 3,9 mg/LSB)."""

    def open(self, bus, cs):
        self.cs = cs

    def xfer2(self, datos):
        reg = datos[0] & 0x3F
        if reg == 0x00:
            return [0, 0xE5]                                  # DEVID
        if reg == 0x39:
            return [0, 16]                                    # FIFO_STATUS
        if reg == 0x30:
            return [0, 0]                                     # INT_SOURCE sin desborde
        if reg == 0x32:
            return [0, 0, 0, 0, 0, 0, 1]                       # x = 0, y = 0, z = 256
        return [0] * len(datos)


class SerieFalsa:
    def __init__(self, *a, **k):
        self.lineas = [_nmea("GPGGA,123519,0532.118,N,07322.068,W,1,08,0.9,2810.0,M,0,M,,"),
                       _nmea("GPRMC,123519,A,0532.118,N,07322.068,W,010.0,084.4,101126,,,A")]
        self.i = 0

    def readline(self):
        time.sleep(0.05)
        self.i += 1
        return self.lineas[self.i % 2]

    def close(self):
        pass


@pytest.fixture
def modulos_falsos(monkeypatch):
    spidev = types.ModuleType("spidev")
    spidev.SpiDev = SpiFalso
    serial = types.ModuleType("serial")
    serial.Serial = SerieFalsa
    gpiozero = types.ModuleType("gpiozero")

    class Entrada:
        def __init__(self, *a, **k):
            self.when_activated = None

    class Led:
        def __init__(self, *a, **k):
            self.estado = None

        def on(self):
            self.estado = "on"

        def off(self):
            self.estado = "off"

        def blink(self, *a):
            self.estado = "blink"
    gpiozero.DigitalInputDevice, gpiozero.LED = Entrada, Led
    for nombre, m in (("spidev", spidev), ("serial", serial), ("gpiozero", gpiozero)):
        monkeypatch.setitem(sys.modules, nombre, m)
    monkeypatch.setitem(sys.modules, "smbus2", None)          # I2C sin conectar (fase 2 del armado)
    monkeypatch.setitem(sys.modules, "board", None)            # sin VL53L0X ni DHT22


def test_modo_pi_arranca_con_sensores_faltantes(modulos_falsos, tmp_path):
    from viaviva.fuentes import FuenteSensores
    from viaviva.nucleo import Nucleo
    f = FuenteSensores()
    n = Nucleo(f.fs, dir_grabaciones=tmp_path)
    f.arrancar(n)
    try:
        n.iniciar_grabacion("pi")
        fin = time.monotonic() + 5
        while time.monotonic() < fin and (n.n_acc < 200 or not n.fix):
            time.sleep(0.05)
        assert n.n_acc >= 200 and n.fix and abs(n.lat - (5 + 32.118 / 60)) < 1e-6
        e = n.estado()
        assert e["sensores"]["adxl345"]["presente"] and e["sensores"]["adxl345_2"]["presente"]
        assert not e["sensores"]["mpu6050"]["presente"] and not e["sensores"]["dht22"]["presente"]
        assert any("Sin conectar" in m and "mpu6050" in m for m in e["mensajes"])
        assert e["latencias"]["lectura_fifo_ms"]["n"] > 5
        carpeta = tmp_path / n.detener_grabacion()
        assert sum(1 for _ in open(carpeta / "Accelerometer_adxl2.csv", encoding="utf-8")) > 100
        z = [float(l.split(",")[3]) for l in open(carpeta / "Accelerometer.csv", encoding="utf-8").readlines()[1:50]]
        assert all(abs(v - 256 * 0.0039 * 9.81) < 1e-6 for v in z)      # 1 g en z
    finally:
        f.cerrar()


class _DHTFalso:
    def __init__(self, inicia=True, lecturas=()):
        self.inicia, self.lecturas, self.error = inicia, list(lecturas), None

    def iniciar(self):
        if not self.inicia:
            self.error = "ModuleNotFoundError: board"
        return self.inicia

    def leer(self):
        r = self.lecturas.pop(0) if self.lecturas else None
        if r is None:
            self.error = "lectura fuera de rango"
        return r


def test_doctor_dht22_solo_da_ok_con_una_lectura_real():
    from viaviva import doctor
    pausas = []
    inf = doctor.Informe()
    doctor.chequear_dht22(inf, _DHTFalso(lecturas=[None, (18.4, 61.0)]), esperar=pausas.append)
    assert inf.filas[-1][0] == doctor.OK and "18.4 °C" in inf.filas[-1][2] and pausas == [2.1]

    inf = doctor.Informe()
    doctor.chequear_dht22(inf, _DHTFalso(lecturas=[]), esperar=pausas.append)   # librería lista, sin sensor
    assert inf.filas[-1][0] == doctor.AVISO and "sin lectura válida en 3 intentos" in inf.filas[-1][2]

    inf = doctor.Informe()
    doctor.chequear_dht22(inf, _DHTFalso(inicia=False), esperar=pausas.append)
    assert inf.filas[-1][0] == doctor.AVISO and "board" in inf.filas[-1][2]


class SpiSinAdxl(SpiFalso):
    """SPI sin ADXL345 montado: DEVID 0x00 (como en la Pi desde el 26-nov)."""

    def xfer2(self, datos):
        return [0] * len(datos)


class SMBusMpu:
    """Bus I2C con un MPU-6050 que da 1 g en z y un golpe de +1 g cada 150 lecturas (sin BH1750)."""

    def __init__(self, *a, **k):
        self.n = 0

    def read_byte_data(self, direccion, registro):
        if direccion != 0x68:
            raise OSError(121, "Remote I/O error")
        return 0x68

    def write_byte_data(self, direccion, registro, valor):
        if direccion != 0x68:
            raise OSError(121, "Remote I/O error")

    def write_byte(self, direccion, valor):
        raise OSError(121, "Remote I/O error")                 # BH1750 ausente

    def read_i2c_block_data(self, direccion, registro, n):
        self.n += 1
        z = 16384 if self.n % 150 == 0 else 8192                # ±4 g: 8192 cuentas = 1 g
        crudo = [0, 0, z, 0, 0, 0, 0]
        return [b for v in crudo for b in int(v).to_bytes(2, "big", signed=True)]


def test_sin_adxl_el_mpu_alimenta_el_detector(modulos_falsos, monkeypatch, tmp_path):
    """Desde el 26-nov los ADXL no están montados: el MPU-6050 pasa a ser el acelerómetro del detector (antes solo se
    grababa en Accelerometer_mpu6050.csv y en el carro habría 0 eventos en vivo)."""
    sys.modules["spidev"].SpiDev = SpiSinAdxl
    smbus2 = types.ModuleType("smbus2")
    smbus2.SMBus = SMBusMpu
    monkeypatch.setitem(sys.modules, "smbus2", smbus2)
    from viaviva import config
    from viaviva.fuentes import FuenteSensores
    from viaviva.nucleo import Nucleo
    f = FuenteSensores()
    n = Nucleo(f.fs, dir_grabaciones=tmp_path)
    f.arrancar(n)
    try:
        assert f.principal == "mpu6050" and n.acelerometro == "mpu6050" and n.fs == config.FS_MPU_HZ
        n.iniciar_grabacion("pi")
        fin = time.monotonic() + 8
        while time.monotonic() < fin and (n.n_eventos_total < 1 or n.n_acc < 300):
            time.sleep(0.05)
        e = n.estado()
        assert e["acelerometro"] == "mpu6050" and not e["acelerometro_sin_datos"] and n.n_acc >= 300
        assert n.n_eventos_total >= 1                         # el golpe de +1 g dispara el detector en vivo
        assert any("MPU-6050" in m and "alimenta el detector" in m for m in e["mensajes"])
        carpeta = tmp_path / n.detener_grabacion()
        filas = open(carpeta / "Accelerometer.csv", encoding="utf-8").read().splitlines()
        assert len(filas) > 200 and filas[0].endswith('"UTC PC (s)"')
        inicio = [x for x in open(carpeta / "bitacora.jsonl", encoding="utf-8") if '"inicio"' in x][0]
        assert '"acelerometro": "mpu6050"' in inicio
    finally:
        f.cerrar()


def test_con_adxl_el_detector_sigue_con_el_adxl(modulos_falsos, tmp_path):
    from viaviva.fuentes import FuenteSensores
    from viaviva.nucleo import Nucleo
    f = FuenteSensores()
    n = Nucleo(f.fs, dir_grabaciones=tmp_path)
    f.arrancar(n)
    try:
        assert f.principal == "adxl345" and n.acelerometro == "adxl345" and n.fs == 200.0
    finally:
        f.cerrar()
