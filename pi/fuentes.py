"""Fuentes de datos del núcleo: los sensores de la Pi o la reproducción de una grabación (demo sin carro).

Las dos entregan lo mismo al `Nucleo` (acc, giro, gps, ambiente, distancia), así que la página web, el detector,
la base y la sincronización funcionan igual con el carro o en la mesa.
"""
from __future__ import annotations

import csv
import io
import math
import statistics
import threading
import time
import zipfile
from pathlib import Path

from pi import config
from pi.nucleo import Nucleo


# ------------------------------------------------------------------------------------------------ sensores reales
class FuenteSensores:
    fs = config.FS_ADXL_HZ

    def __init__(self, al_apagar=None):
        from pi import sensores as s
        self.s = s
        self.al_apagar = al_apagar           # función: apagado seguro (pulsador sostenido 3 s)
        self.parar = threading.Event()
        self.adxl = s.ADXL345()
        self.gps = s.GPS()
        self.dht = s.DHT22()
        self.vl = s.VL53L0X()
        self.bus = None
        try:
            from smbus2 import SMBus
            self.bus = SMBus(config.I2C_BUS)
        except Exception as err:
            self.error_i2c = str(err)
        self.mpu = s.MPU6050(self.bus)
        self.luz = s.BH1750(self.bus)
        self.led = self.boton = None
        self.t0 = time.monotonic()

    def t(self) -> float:
        return time.monotonic() - self.t0

    def arrancar(self, n: Nucleo) -> None:
        self.n = n
        n.base_epoch = time.time() - self.t()
        for sensor in (self.adxl, self.gps, self.dht, self.vl):
            sensor.iniciar()
        if self.bus is not None:
            self.mpu.iniciar()
            self.luz.iniciar()
        n.sensores = {x.nombre: x for x in (self.adxl, self.mpu, self.vl, self.luz, self.gps, self.dht)}
        for nombre, f in (("adq-adxl", self._hilo_adxl), ("i2c", self._hilo_i2c), ("gps", self._hilo_gps),
                          ("ambiente", self._hilo_ambiente), ("led", self._hilo_led)):
            threading.Thread(target=f, daemon=True, name=nombre).start()
        self._pulsador()

    # --- ADXL345: espera la interrupción (o sondea), vacía la FIFO y entrega el lote
    def _hilo_adxl(self) -> None:
        if not self.adxl.presente:
            return
        try:                                   # prioridad alta si el servicio tiene permiso (CAP_SYS_NICE)
            import os
            os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(50))
        except Exception:
            pass
        k, t_base = 0, self.t()
        marca_irq = [None]
        if self.adxl.int1 is not None:
            def al_subir():
                marca_irq[0] = time.perf_counter()
                self.adxl.hay_datos.set()
            self.adxl.int1.when_activated = al_subir
        while not self.parar.is_set():
            self.adxl.hay_datos.wait(0.05)
            self.adxl.hay_datos.clear()
            t_lectura = time.perf_counter()
            if marca_irq[0] is not None:
                self.n.latencias["irq_a_lectura_ms"].agregar((t_lectura - marca_irq[0]) * 1e3)
                marca_irq[0] = None
            try:
                lote = self.adxl.leer_fifo()
            except Exception as err:
                self.adxl.falla(err)
                time.sleep(0.5)
                continue
            self.n.latencias["lectura_fifo_ms"].agregar((time.perf_counter() - t_lectura) * 1e3)
            if not lote:
                continue
            ahora = self.t()
            if abs(t_base + (k + len(lote)) / self.fs - ahora) > 0.2:   # desborde o reloj corrido: re-anclar
                t_base, k = ahora - len(lote) / self.fs, 0
            filas = [(t_base + (k + i) / self.fs, *m) for i, m in enumerate(lote)]
            k += len(lote)
            self.n.acc(filas)

    # --- I2C: MPU-6050 a 100 Hz; VL53L0X cuando tiene dato; BH1750 cada 1 s
    def _hilo_i2c(self) -> None:
        periodo, siguiente, sig_luz = 1.0 / config.FS_MPU_HZ, time.monotonic(), 0.0
        lote_acc, lote_giro = [], []
        while not self.parar.is_set():
            inicio = time.perf_counter()
            t = self.t()
            if self.mpu.presente:
                try:
                    a, g = self.mpu.leer()
                    lote_acc.append((t, *a))
                    lote_giro.append((t, *g))
                except Exception as err:
                    self.mpu.falla(err)
            if self.vl.presente:
                try:
                    mm = self.vl.leer()
                    if mm is not None:
                        self.n.distancia(t, mm)
                except Exception as err:
                    self.vl.falla(err)
            if self.luz.presente and time.monotonic() >= sig_luz:
                sig_luz = time.monotonic() + config.PERIODO_LUZ_S
                try:
                    self.n.ambiente(t, lux=self.luz.leer(), sensor="bh1750")
                except Exception as err:
                    self.luz.falla(err)
            if len(lote_giro) >= 10:
                self.n.giro(lote_giro)
                self.n.acc_mpu(lote_acc)
                lote_acc, lote_giro = [], []
            self.n.latencias["ciclo_i2c_ms"].agregar((time.perf_counter() - inicio) * 1e3)
            siguiente += periodo
            espera = siguiente - time.monotonic()
            if espera > 0:
                time.sleep(espera)
            else:
                siguiente = time.monotonic()

    def _hilo_gps(self) -> None:
        while not self.parar.is_set():
            if not self.gps.presente:
                time.sleep(5)
                self.gps.iniciar()
                continue
            try:
                r = self.gps.leer_linea()
                if r is not None:
                    self.n.gps(self.t(), r["lat"], r["lon"], r["alt"], r["vel_ms"], r["rumbo"], r["precision_m"],
                               r["sat"], r["utc_epoch"] if r["valido"] else None)
            except Exception as err:            # 5 s sin datos → reabrir el puerto (como el nodo ESP32)
                self.gps.falla(err)
                try:
                    self.gps.puerto.close()
                except Exception:
                    pass
                self.gps.presente = False

    def _hilo_ambiente(self) -> None:
        while not self.parar.wait(config.PERIODO_AMBIENTE_S):
            if self.dht.presente:
                r = self.dht.leer()
                if r is not None:
                    self.n.ambiente(self.t(), temperatura=r[0], humedad=r[1], sensor="dht22")

    # --- pulsador y LED
    def _pulsador(self) -> None:
        try:
            from gpiozero import LED, Button
            self.led = LED(config.PIN_LED)
            self.boton = Button(config.PIN_PULSADOR, pull_up=True, bounce_time=0.05,
                                hold_time=config.SOSTENER_APAGADO_S)
            sostenido = [False]

            def al_sostener():
                sostenido[0] = True
                if self.al_apagar:
                    self.al_apagar("pulsador")

            def al_soltar():
                if not sostenido[0]:
                    self.n.etiquetar("otro", origen="boton")      # marca rápida; se corrige en la web
                sostenido[0] = False
            self.boton.when_held = al_sostener
            self.boton.when_released = al_soltar
        except Exception as err:
            self.n.aviso(f"Pulsador/LED no disponibles: {err}")

    def _hilo_led(self) -> None:
        modo = None
        while not self.parar.wait(1.0):
            if self.led is None:
                continue
            falla = not self.adxl.presente or time.monotonic() - self.n.mono_ultimo > 2.0
            nuevo = "falla" if falla else "grabando" if self.n.sesion else "listo"
            if nuevo != modo:
                modo = nuevo
                if modo == "falla":
                    self.led.blink(0.1, 0.1)
                elif modo == "grabando":
                    self.led.blink(0.5, 0.5)
                else:
                    self.led.on()

    def cerrar(self) -> None:
        self.parar.set()
        if self.led is not None:
            self.led.off()


# ------------------------------------------------------------------------------------------------ reproducción
def _leer_tabla(ruta: Path, nombre: str) -> list[list[float]]:
    """CSV de phyphox (iOS o Android: se lee por posición) o de la Pi, desde carpeta o zip. [] si no existe."""
    texto = None
    if ruta.is_dir():
        p = ruta / nombre
        if not p.exists():                         # meta/time.csv va en una subcarpeta
            p = next(iter(sorted(ruta.glob(f"*/{nombre}"))), p)
        texto = p.read_text(encoding="utf-8-sig") if p.exists() else None
    elif zipfile.is_zipfile(ruta):
        with zipfile.ZipFile(ruta) as z:
            cand = [n for n in z.namelist() if n.endswith(nombre)]
            texto = z.read(cand[0]).decode("utf-8-sig") if cand else None
    if texto is None:
        return []

    def num(v):
        try:
            return float(v)
        except ValueError:
            return math.nan
    return [[num(v) for v in f] for f in list(csv.reader(io.StringIO(texto)))[1:] if f]


def _inicio_epoch(ruta: Path) -> float | None:
    filas = _leer_tabla(ruta, "time.csv")
    return filas[0][2] if filas and len(filas[0]) > 2 and not math.isnan(filas[0][2]) else None


class FuenteReproduccion:
    """Reproduce una grabación (export de phyphox o carpeta de la Pi) en tiempo real × `velocidad`.
    Los eventos se guardan con origen 'simulado': nunca se mezclan con datos reales del modelo de riesgo."""

    def __init__(self, ruta: Path, velocidad: float = 1.0, bucle: bool = False):
        self.ruta, self.velocidad, self.bucle = Path(ruta), velocidad, bucle
        self.tablas = {"acc": _leer_tabla(self.ruta, "Accelerometer.csv"),
                       "giro": _leer_tabla(self.ruta, "Gyroscope.csv"),
                       "gps": _leer_tabla(self.ruta, "Location.csv"),
                       "ambiente": _leer_tabla(self.ruta, "Ambiente.csv"),
                       "distancia": _leer_tabla(self.ruta, "Distancia_vl53l0x.csv")}
        acc = self.tablas["acc"]
        if len(acc) < 10:
            raise ValueError(f"{self.ruta} no tiene Accelerometer.csv con datos")
        dts = [b[0] - a[0] for a, b in zip(acc[:2000], acc[1:2001]) if b[0] > a[0]]
        self.fs = round(1.0 / statistics.median(dts), 1)
        self.duracion_s = acc[-1][0] - acc[0][0]
        self.inicio_epoch = _inicio_epoch(self.ruta)
        self.parar = threading.Event()
        self.terminada = threading.Event()
        self.vueltas = 0

    def arrancar(self, n: Nucleo) -> None:
        self.n = n
        if self.inicio_epoch:
            n.base_epoch = self.inicio_epoch
        n.sensores = {"reproduccion": _EstadoReproduccion(self)}
        threading.Thread(target=self._hilo, daemon=True, name="reproduccion").start()

    def _hilo(self) -> None:
        paso = 0.05                                      # entrega cada 50 ms de reloj, como llegarían los lotes
        while not self.parar.is_set():
            idx = dict.fromkeys(self.tablas, 0)
            desfase = self.vueltas * (self.duracion_s + 1.0)   # en bucle el tiempo sigue creciendo
            t_sim, t_fin = self.tablas["acc"][0][0], self.tablas["acc"][-1][0]
            inicio = time.monotonic()
            while t_sim <= t_fin and not self.parar.is_set():
                t_sim = self.tablas["acc"][0][0] + (time.monotonic() - inicio) * self.velocidad
                for clave, filas in self.tablas.items():
                    i0 = i = idx[clave]
                    while i < len(filas) and filas[i][0] <= t_sim:
                        i += 1
                    if i > i0:
                        self._entregar(clave, filas[i0:i], desfase)
                        idx[clave] = i
                time.sleep(paso)
            self.vueltas += 1
            if not self.bucle:
                break
        self.terminada.set()

    def _entregar(self, clave: str, filas, desfase: float) -> None:
        n = self.n
        if clave == "acc":
            n.acc([(f[0] + desfase, f[1], f[2], f[3]) for f in filas if len(f) >= 4])
        elif clave == "giro":
            n.giro([(f[0] + desfase, f[1], f[2], f[3]) for f in filas if len(f) >= 4])
        elif clave == "gps":
            for f in filas:
                f = f + [math.nan] * (8 - len(f))
                n.gps(f[0] + desfase, f[1], f[2], f[3], f[4], f[5], f[6], 0)
        elif clave == "ambiente":
            for f in filas:
                v = lambda x: None if math.isnan(x) else x
                n.ambiente(f[0] + desfase, v(f[1]), v(f[2]), v(f[3]), "reproduccion")
        elif clave == "distancia":
            for f in filas:
                n.distancia(f[0] + desfase, f[1])

    def cerrar(self) -> None:
        self.parar.set()


class _EstadoReproduccion:
    def __init__(self, f: FuenteReproduccion):
        self.f = f

    def estado(self) -> dict:
        return {"presente": True, "archivo": self.f.ruta.name, "fs_hz": self.f.fs,
                "duracion_s": round(self.f.duracion_s, 1), "velocidad": self.f.velocidad,
                "vueltas": self.f.vueltas, "terminada": self.f.terminada.is_set(), "error": None}
