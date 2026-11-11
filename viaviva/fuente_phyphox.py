"""Fuente en vivo: phyphox en el iPhone por el acceso remoto (HTTP), leída desde el PC conectado a su punto de acceso.

- Una petición `/get` cada 0,25 s pide, para cada buffer, solo lo nuevo (tiempo > el último recibido).
- Si se cae el hotspot, reintenta cada 1–5 s y avisa; phyphox sigue guardando en el celular, así que al volver se
  piden las muestras atrasadas y **no se pierde nada** mientras phyphox siga midiendo.
- Si phyphox empieza otra medición (el tiempo vuelve a 0), el tiempo de la sesión continúa con un desplazamiento.
- Latencia de cada petición (media ± desviación) en `latencias.http_phyphox_ms` para R7.
Experimento "VÍA VIVA 2.0" (06_CAMPO): buffers accX/Y/Z + acc_time, gyroX/Y/Z + gyro_time, gpsLat/Lon/Z/V/Dir/Accuracy/
ZAccuracy + gps_time.
"""
from __future__ import annotations

import json
import math
import threading
import time
import urllib.error
import urllib.request

from viaviva import config
from viaviva.nucleo import Nucleo

GRUPOS = {
    "acc": ("acc_time", ["accX", "accY", "accZ"]),
    "giro": ("gyro_time", ["gyroX", "gyroY", "gyroZ"]),
    "gps": ("gps_time", ["gpsLat", "gpsLon", "gpsZ", "gpsV", "gpsDir", "gpsAccuracy", "gpsZAccuracy"]),
}


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return math.nan


class ClientePhyphox:
    def __init__(self, url: str = config.PHYPHOX_URL, timeout: float = 2.0):
        self.url = url.rstrip("/")
        self.timeout = timeout

    def _json(self, ruta: str) -> dict:
        with urllib.request.urlopen(self.url + ruta, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def config(self) -> dict:
        return self._json("/config")

    def control(self, cmd: str) -> None:
        self._json(f"/control?cmd={cmd}")

    def nuevos(self, desde: dict[str, float]) -> dict:
        """Datos con tiempo > desde[grupo] para todos los grupos, en UNA petición."""
        partes = []
        for g, (tiempo, valores) in GRUPOS.items():
            t0 = repr(desde[g])
            partes.append(f"{tiempo}={t0}")
            partes += [f"{v}={t0}|{tiempo}" for v in valores]
        return self._json("/get?" + "&".join(partes))


def buffers_faltantes(cfg: dict) -> list[str]:
    hay = {b["name"] if isinstance(b, dict) else str(b) for b in cfg.get("buffers", [])}
    pedidos = {n for t, vs in GRUPOS.values() for n in [t, *vs]}
    return sorted(pedidos - hay) if hay else []


def filas_de(resp: dict, grupo: str) -> list[list[float]]:
    buf = resp.get("buffer", {})
    tiempo, valores = GRUPOS[grupo]
    cols = [buf.get(n, {}).get("buffer", []) for n in [tiempo, *valores]]
    n = min(len(c) for c in cols)
    return [[_num(c[i]) for c in cols] for i in range(n)]


class FuentePhyphox:
    fs = config.FS_PHYPHOX_HZ

    def __init__(self, url: str = config.PHYPHOX_URL, iniciar: bool = False, intervalo_s: float = 0.25,
                 cliente: ClientePhyphox | None = None):
        self.cliente = cliente or ClientePhyphox(url)
        self.iniciar, self.intervalo = iniciar, intervalo_s
        self.parar = threading.Event()
        self.midiendo = None
        self.ultimo_ok = None
        self.error: str | None = None
        self.peticiones = 0
        self.partes = 1

    def arrancar(self, n: Nucleo) -> None:
        self.n = n
        n.sensores = {"phyphox": _EstadoPhyphox(self)}
        threading.Thread(target=self._hilo, daemon=True, name="phyphox").start()

    def _hilo(self) -> None:
        n = self.n
        desde = dict.fromkeys(GRUPOS, -1.0)
        desplazamiento, sesion_ph, base_lista, espera = 0.0, None, False, 1.0
        if self.iniciar:
            try:
                self.cliente.control("start")
            except Exception as err:
                n.aviso(f"No se pudo iniciar phyphox: {err}")
        while not self.parar.is_set():
            t0 = time.perf_counter()
            try:
                resp = self.cliente.nuevos(desde)
            except (urllib.error.URLError, OSError, TimeoutError, ValueError) as err:
                self.error = f"{type(err).__name__}: {err}"[:160]
                n.conexion(False, f"con phyphox ({self.cliente.url})")
                self.parar.wait(espera)
                espera = min(5.0, espera * 1.5)
                continue
            espera = 1.0
            self.peticiones += 1
            self.error = None
            self.ultimo_ok = time.monotonic()
            n.latencias["http_phyphox_ms"].agregar((time.perf_counter() - t0) * 1e3)
            n.conexion(True)
            estado = resp.get("status", {}) or {}
            self.midiendo = estado.get("measuring")
            sesion = estado.get("session")
            recibido = time.time()
            filas = {g: filas_de(resp, g) for g in GRUPOS}
            reinicio = (sesion_ph is not None and sesion is not None and sesion != sesion_ph)
            if filas["acc"] and desde["acc"] > 0 and filas["acc"][0][0] < desde["acc"] - 1.0:
                reinicio = True
            if reinicio:                              # phyphox empezó otra medición: el tiempo volvió a 0
                desplazamiento = n.ultimo_t + 1.0
                desde = dict.fromkeys(GRUPOS, -1.0)
                self.partes += 1
                n.aviso(f"phyphox empezó una medición nueva (parte {self.partes}); el tiempo sigue desde "
                        f"{desplazamiento:.1f} s", "reinicio_phyphox")
                sesion_ph = sesion
                continue
            sesion_ph = sesion
            if filas["acc"]:
                if not base_lista:                    # t = 0 de phyphox en la hora del PC
                    n.base_epoch = recibido - (filas["acc"][-1][0] + desplazamiento)
                    base_lista = True
                n.acc([(f[0] + desplazamiento, f[1], f[2], f[3]) for f in filas["acc"]], recibido)
                desde["acc"] = filas["acc"][-1][0]
            if filas["giro"]:
                n.giro([(f[0] + desplazamiento, f[1], f[2], f[3]) for f in filas["giro"]], recibido)
                desde["giro"] = filas["giro"][-1][0]
            for f in filas["gps"]:
                n.gps(f[0] + desplazamiento, f[1], f[2], f[3], f[4], f[5], f[6], 0, None, recibido)
            if filas["gps"]:
                desde["gps"] = filas["gps"][-1][0]
            self.parar.wait(max(0.0, self.intervalo - (time.perf_counter() - t0)))

    def cerrar(self) -> None:
        self.parar.set()


class _EstadoPhyphox:
    def __init__(self, f: FuentePhyphox):
        self.f = f

    def estado(self) -> dict:
        edad = None if self.f.ultimo_ok is None else round(time.monotonic() - self.f.ultimo_ok, 1)
        return {"presente": self.f.error is None and self.f.ultimo_ok is not None, "url": self.f.cliente.url,
                "midiendo": self.f.midiendo, "peticiones": self.f.peticiones, "edad_s": edad, "partes": self.f.partes,
                "error": self.f.error or (None if self.f.midiendo is not False else "phyphox en pausa: toque ▶")}
