"""Salud de la Pi para la página web y para R7: % de CPU, temperatura, RAM, estrangulamiento por voltaje/calor.

Lee /proc y /sys directamente (sin psutil) para que funcione igual en la Pi; en Windows/PC devuelve lo que pueda.
Cada 10 s deja una línea en data/logs/r7_pi.jsonl con las latencias del núcleo (media ± desviación, Welford).
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from pi import config
from pi.nucleo import Welford


def _leer(ruta: str) -> str | None:
    try:
        return Path(ruta).read_text().strip()
    except OSError:
        return None


class Sistema:
    def __init__(self):
        self._cpu_prev = None
        self.cpu_pct = Welford()
        self.temp_c = Welford()
        self.rss_mb = Welford()
        self.inicio = time.monotonic()

    def _cpu(self) -> float | None:
        """% de CPU de toda la Pi entre dos llamadas (/proc/stat)."""
        linea = _leer("/proc/stat")
        if not linea:
            return None
        v = [int(x) for x in linea.splitlines()[0].split()[1:]]
        ocio, total = v[3] + v[4], sum(v)
        prev, self._cpu_prev = self._cpu_prev, (ocio, total)
        if prev is None or total == prev[1]:
            return None
        return round(100.0 * (1 - (ocio - prev[0]) / (total - prev[1])), 1)

    @staticmethod
    def temperatura() -> float | None:
        t = _leer("/sys/class/thermal/thermal_zone0/temp")
        return round(int(t) / 1000, 1) if t else None

    @staticmethod
    def memoria() -> dict:
        info = _leer("/proc/meminfo")
        rss = None
        estado = _leer("/proc/self/status")
        if estado:
            for linea in estado.splitlines():
                if linea.startswith("VmRSS:"):
                    rss = round(int(linea.split()[1]) / 1024, 1)
        if not info:
            return {"proceso_mb": rss}
        m = {l.split(":")[0]: int(l.split()[1]) for l in info.splitlines()}
        return {"proceso_mb": rss, "total_mb": round(m["MemTotal"] / 1024),
                "disponible_mb": round(m["MemAvailable"] / 1024)}

    @staticmethod
    def estrangulamiento() -> dict | None:
        """vcgencmd get_throttled: bit 0 = bajo voltaje AHORA, bit 16 = hubo bajo voltaje desde el arranque.
        Con la toma de 12 V del carro es el dato que dice si el adaptador USB-C alcanza (5 V / 3 A)."""
        if not shutil.which("vcgencmd"):
            return None
        try:
            s = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=2).stdout
            v = int(s.strip().split("=")[1], 16)
        except Exception:
            return None
        return {"bajo_voltaje": bool(v & 0x1), "estrangulada": bool(v & 0x4), "limite_temp": bool(v & 0x8),
                "hubo_bajo_voltaje": bool(v & 0x10000), "hubo_estrangulamiento": bool(v & 0x40000)}

    def disco(self) -> dict:
        try:
            u = shutil.disk_usage(config.DIR_GRABACIONES if config.DIR_GRABACIONES.exists() else config.RAIZ)
            return {"libre_gb": round(u.free / 1e9, 1), "total_gb": round(u.total / 1e9, 1)}
        except OSError:
            return {}

    def estado(self) -> dict:
        cpu, temp, mem = self._cpu(), self.temperatura(), self.memoria()
        if cpu is not None:
            self.cpu_pct.agregar(cpu)
        if temp is not None:
            self.temp_c.agregar(temp)
        if mem.get("proceso_mb") is not None:
            self.rss_mb.agregar(mem["proceso_mb"])
        return {"equipo": _leer("/proc/device-tree/model") or platform.node(), "cpu_pct": cpu, "temp_c": temp,
                "memoria": mem, "estrangulamiento": self.estrangulamiento(), "disco": self.disco(),
                "encendido_s": round(time.monotonic() - self.inicio), "nucleos": os.cpu_count()}


def registrar_r7(nucleo, sistema: Sistema, parar: threading.Event, periodo_s: float = 10.0,
                 ruta: Path = config.LOG_R7) -> None:
    """Hilo: cada `periodo_s` agrega una línea JSON con latencias (Welford acumulado) y salud del sistema."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    while not parar.wait(periodo_s):
        s = sistema.estado()
        fila = {"ts_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "equipo": s["equipo"],
                "origen": nucleo.origen, "fs_hz": nucleo.fs, "grabando": nucleo.sesion is not None,
                "muestras": nucleo.n_acc, "cpu_pct": s["cpu_pct"], "temp_c": s["temp_c"],
                "memoria": s["memoria"], "estrangulamiento": s["estrangulamiento"],
                "cpu_resumen": sistema.cpu_pct.resumen(1), "temp_resumen": sistema.temp_c.resumen(1),
                "latencias": {k: w.resumen() for k, w in nucleo.latencias.items() if w.n},
                "sensores": {k: {"fallos": v.get("fallos"), "desbordes_fifo": v.get("desbordes_fifo")}
                             for k, v in ((k, s_.estado()) for k, s_ in nucleo.sensores.items())}}
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
