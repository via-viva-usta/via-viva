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
import urllib.parse
import urllib.request

from viaviva import config
from viaviva.nucleo import Nucleo

GRUPOS = {   # nombres del experimento "VÍA VIVA 2.0"; si el experimento usa otros, se leen de /config
    "acc": ("acc_time", ["accX", "accY", "accZ"]),
    "giro": ("gyro_time", ["gyroX", "gyroY", "gyroZ"]),
    "gps": ("gps_time", ["gpsLat", "gpsLon", "gpsZ", "gpsV", "gpsDir", "gpsAccuracy", "gpsZAccuracy"]),
}
FUENTES = {"acc": ("accelerometer", "linear_acceleration"), "giro": ("gyroscope",), "gps": ("location",)}
SALIDAS = {"acc": ["x", "y", "z"], "giro": ["x", "y", "z"],
           "gps": ["lat", "lon", "z", "v", "dir", "accuracy", "zAccuracy"]}
OBLIGATORIAS = {"acc": 3, "giro": 3, "gps": 2}     # cuántas de las salidas (en orden) no pueden faltar
PUERTOS = (80, 8080)                               # iOS responde en el 80; Android en el 8080


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return math.nan


def mapear_buffers(cfg: dict) -> dict:
    """Buffers REALES del experimento, leídos de `inputs` en /config (sensor → nombre de cada salida).
    Lo que no se pueda leer queda con los nombres por defecto de "VÍA VIVA 2.0"."""
    grupos = {}
    for g, fuentes in FUENTES.items():
        grupos[g] = GRUPOS[g]
        for fuente in fuentes:
            entrada = next((e for e in cfg.get("inputs", []) if e.get("source") == fuente), None)
            if not entrada:
                continue
            salidas: dict = {}
            for o in entrada.get("outputs", []):
                salidas.update(o)
            claves = SALIDAS[g]
            if salidas.get("t") and all(salidas.get(k) for k in claves[: OBLIGATORIAS[g]]):
                grupos[g] = (salidas["t"], [salidas.get(k) for k in claves])
                break
    return grupos


def buffers_faltantes(cfg: dict, grupos: dict | None = None) -> list[str]:
    """Buffers obligatorios (aceleración y posición) que el experimento del celular no tiene."""
    grupos = grupos or mapear_buffers(cfg)
    hay = {b["name"] if isinstance(b, dict) else str(b) for b in cfg.get("buffers", [])}
    if not hay:
        return []
    pedidos = [n for g in ("acc", "gps") for n in [grupos[g][0], *grupos[g][1][: OBLIGATORIAS[g]]]]
    return sorted(n for n in pedidos if n not in hay)


def filas_de(resp: dict, grupo: str, grupos: dict | None = None) -> list[list[float]]:
    """Filas [t, valores…] del grupo. Las salidas obligatorias mandan el largo; las opcionales que falten van NaN."""
    buf = resp.get("buffer", {})
    tiempo, valores = (grupos or GRUPOS)[grupo]
    cols = [buf.get(n, {}).get("buffer", []) if n else [] for n in [tiempo, *valores]]
    n = min(len(c) for c in cols[: 1 + OBLIGATORIAS[grupo]])
    return [[_num(c[k]) if k < len(c) else math.nan for c in cols] for k in range(n)]


def candidatos(url: str) -> list[str]:
    """La URL dada primero y luego el mismo equipo en los otros puertos de phyphox (80 y 8080)."""
    u = urllib.parse.urlsplit(url if "//" in url else "http://" + url)
    host = u.hostname or "172.20.10.1"
    lista = [f"http://{host}" + (f":{u.port}" if u.port and u.port != 80 else "")]
    lista += [f"http://{host}" + ("" if p == 80 else f":{p}") for p in PUERTOS]
    return list(dict.fromkeys(lista))


def descubrir(url: str, timeout: float = 1.5) -> tuple[str | None, dict]:
    """Prueba la URL y los puertos 80/8080; devuelve la que responde /config (y esa configuración)."""
    for cand in candidatos(url):
        try:
            with urllib.request.urlopen(cand + "/config", timeout=timeout) as r:
                cfg = json.loads(r.read().decode("utf-8"))
            if isinstance(cfg, dict) and ("buffers" in cfg or "inputs" in cfg):
                return cand, cfg
        except (urllib.error.URLError, OSError, ValueError):
            continue
    return None, {}


class ClientePhyphox:
    def __init__(self, url: str = config.PHYPHOX_URL, timeout: float = 2.0, grupos: dict | None = None):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.grupos = grupos or GRUPOS

    def _json(self, ruta: str) -> dict:
        with urllib.request.urlopen(self.url + ruta, timeout=self.timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def config(self) -> dict:
        return self._json("/config")

    def conectar(self) -> dict | None:
        """Autodetecta el puerto y mapea los buffers. None si phyphox no responde."""
        url, cfg = descubrir(self.url, min(self.timeout, 1.5))
        if url is None:
            return None
        self.url, self.grupos = url, mapear_buffers(cfg)
        return cfg

    def control(self, cmd: str) -> None:
        self._json(f"/control?cmd={cmd}")

    def nuevos(self, desde: dict[str, float]) -> dict:
        """Datos con tiempo > desde[grupo] para todos los grupos, en UNA petición."""
        partes = []
        for g, (tiempo, valores) in self.grupos.items():
            t0 = repr(desde[g])
            partes.append(f"{tiempo}={t0}")
            partes += [f"{v}={t0}|{tiempo}" for v in valores if v]
        return self._json("/get?" + "&".join(partes))


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
        self.latencia_ms: float | None = None    # última petición /get (panel de conexión)

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
        fallos = 0
        if self.cliente.conectar() is None:
            n.aviso(f"phyphox no responde en {self.cliente.url} (se probaron los puertos 80 y 8080); se sigue "
                    "intentando")
        while not self.parar.is_set():
            t0 = time.perf_counter()
            try:
                resp = self.cliente.nuevos(desde)
            except (urllib.error.URLError, OSError, TimeoutError, ValueError) as err:
                self.error = f"{type(err).__name__}: {err}"[:160]
                n.conexion(False, f"con phyphox ({self.cliente.url})")
                fallos += 1
                if fallos % 3 == 0:                   # ¿cambió de puerto o de experimento?
                    self.cliente.conectar()
                self.parar.wait(espera)
                espera = min(5.0, espera * 1.5)
                continue
            espera, fallos = 1.0, 0
            self.peticiones += 1
            self.error = None
            self.ultimo_ok = time.monotonic()
            self.latencia_ms = round((time.perf_counter() - t0) * 1e3, 1)
            n.latencias["http_phyphox_ms"].agregar(self.latencia_ms)
            n.conexion(True)
            estado = resp.get("status", {}) or {}
            self.midiendo = estado.get("measuring")
            sesion = estado.get("session")
            recibido = time.time()
            filas = {g: filas_de(resp, g, self.cliente.grupos) for g in GRUPOS}
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
