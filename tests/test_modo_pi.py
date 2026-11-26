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


@pytest.mark.parametrize("obligatorio,esperado", [(False, "AVISO"), (True, "FALTA")])
def test_doctor_adxl1_sin_montar_es_aviso_salvo_que_sea_obligatorio(monkeypatch, obligatorio, esperado):
    """Desde el 26-nov el ADXL #1 no está montado: el doctor no debe dar FALTA (decisión de AC).
    Con PI_ADXL_OBLIGATORIO=1 vuelve a exigirlo."""
    from viaviva import config, doctor
    from viaviva import sensores as s

    class _AdxlAusente:
        def __init__(self, *a, **k):
            self.error = "RuntimeError: DEVID 0x00 (esperado 0xE5): revisar cableado SPI"

        def iniciar(self):
            return False

    monkeypatch.setattr(s, "ADXL345", _AdxlAusente)
    monkeypatch.setattr(config, "ADXL_OBLIGATORIO", obligatorio)
    monkeypatch.setitem(sys.modules, "smbus2", None)
    monkeypatch.setattr(s.GPS, "iniciar", lambda self: False)
    monkeypatch.setattr(doctor, "chequear_dht22", lambda inf, dht: None)
    inf = doctor.Informe()
    doctor.chequear_pi(inf)
    fila = next(f for f in inf.filas if f[1] == "ADXL345 #1 (SPI CE0)")
    assert fila[0] == esperado and "DEVID 0x00" in fila[2]
    assert (fila[2].startswith("no montado")) == (not obligatorio)
