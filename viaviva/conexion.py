"""Panel de conexión de la app: red del PC, phyphox del iPhone A, Raspberry Pi en la red y QR de /marcar.

Todo con tiempos cortos y en hilos aparte: la pantalla nunca se queda esperando a la red.
"""
from __future__ import annotations

import ipaddress
import json
import os
import platform
import re
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from viaviva import config
from viaviva.fuente_phyphox import buffers_faltantes, candidatos

RED_IPHONE = ipaddress.ip_network("172.20.10.0/28")     # punto de acceso personal de iOS
PI_CANDIDATOS = ("http://raspberrypi.local", "http://via-viva.local", "http://192.168.4.1")


def _sin_ventana() -> dict:
    """En Windows, que los comandos de red no abran una consola (la app corre con pythonw)."""
    return {"creationflags": 0x08000000} if platform.system() == "Windows" else {}


def ip_local() -> str | None:
    """IP de este equipo en la red por la que sale (no envía nada: solo elige la interfaz)."""
    from viaviva import doctor
    ip = doctor.ip_local()
    if ip and not ip.startswith("127."):
        return ip
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None
    finally:
        s.close()


def nombre_wifi() -> str | None:
    try:
        sistema = platform.system()
        if sistema == "Windows":
            r = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True, text=True, timeout=4,
                               encoding="utf-8", errors="replace", **_sin_ventana())
            m = re.search(r"^\s*SSID\s*:\s*(.+)$", r.stdout, re.MULTILINE)
        elif sistema == "Darwin":
            r = subprocess.run(["networksetup", "-getairportnetwork", "en0"], capture_output=True, text=True, timeout=4)
            m = re.search(r":\s*(.+)$", r.stdout.strip())
        else:
            r = subprocess.run(["iwgetid", "-r"], capture_output=True, text=True, timeout=4)
            return r.stdout.strip() or None
        return m.group(1).strip() if m else None
    except (OSError, subprocess.SubprocessError):
        return None


def red() -> dict:
    ip = ip_local()
    en_iphone = bool(ip) and ipaddress.ip_address(ip) in RED_IPHONE
    wifi = nombre_wifi()
    if en_iphone:
        mensaje = "Conectado al punto de acceso de un iPhone"
    elif ip:
        mensaje = "Conectado a una red, pero no a un iPhone (el iPhone A da direcciones 172.20.10.x)"
    else:
        mensaje = "Sin red: conecte el PC al WiFi del iPhone A (Punto de acceso personal)"
    return {"ip": ip, "wifi": wifi, "hotspot_iphone": en_iphone, "mensaje": mensaje,
            "en_docker": bool(os.getenv("VIAVIVA_EN_DOCKER"))}


def probar_phyphox(url: str | None = None, timeout: float = 1.5) -> dict:
    """Prueba la URL y los puertos 80 y 8080: responde /config, cuánto tarda y si el experimento sirve."""
    url = url or config.PHYPHOX_URL
    intentos = []
    for cand in candidatos(url):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(cand + "/config", timeout=timeout) as r:
                cfg = json.loads(r.read().decode("utf-8"))
            ms = round((time.perf_counter() - t0) * 1e3, 1)
        except (urllib.error.URLError, OSError, ValueError) as err:
            intentos.append({"url": cand, "error": str(getattr(err, "reason", err))[:120]})
            continue
        faltan = buffers_faltantes(cfg)
        puerto = urllib.parse.urlsplit(cand).port or 80
        return {"ok": not faltan, "url": cand, "puerto": puerto, "latencia_ms": ms,
                "experimento": cfg.get("title"), "faltan": faltan, "intentos": intentos,
                "mensaje": (f"phyphox responde en el puerto {puerto} ({ms} ms)." if not faltan else
                            f"phyphox responde, pero el experimento no es «VÍA VIVA 2.0»: faltan {', '.join(faltan)}.")}
    return {"ok": False, "url": url, "puerto": None, "latencia_ms": None, "experimento": None, "faltan": [],
            "intentos": intentos,
            "mensaje": "phyphox no responde (se probaron los puertos 80 y 8080). Revise: PC en el WiFi del iPhone A, "
                       "«Permitir acceso remoto» activado y ▶ en phyphox."}


def probar_pi(timeout: float = 1.2) -> dict:
    """Busca la Raspberry Pi en la red (VIAVIVA_PI_URL, nombres .local y 192.168.4.1) por /api/hora."""
    lista = [u for u in [os.getenv("VIAVIVA_PI_URL", "").strip(), *PI_CANDIDATOS] if u]

    def una(base: str):
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(base.rstrip("/") + "/api/hora", timeout=timeout) as r:
                json.loads(r.read().decode("utf-8"))["utc"]
            return {"url": base, "latencia_ms": round((time.perf_counter() - t0) * 1e3, 1)}
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=len(lista)) as ex:
        hallada = next((r for r in ex.map(una, lista) if r), None)
    if hallada:
        return {"encontrada": True, **hallada, "mensaje": f"Raspberry Pi en {hallada['url']}"}
    return {"encontrada": False, "url": None, "buscadas": lista,
            "mensaje": "No hay una Raspberry Pi en esta red (es normal en la salida con phyphox)."}


def qr_svg(texto: str) -> str | None:
    """QR en SVG (segno, sin internet). None si segno no está instalado."""
    try:
        import segno
    except ImportError:
        return None
    import io
    salida = io.BytesIO()
    segno.make(texto, error="m").save(salida, kind="svg", scale=6, border=2, dark="#0a0a0a", light="#ffffff",
                                      xmldecl=False, svgns=True)
    return salida.getvalue().decode("utf-8")


class Vigia:
    """Guarda el último estado de la red y de la Pi; se refresca en segundo plano (nunca bloquea una petición)."""

    def __init__(self, cada_s: float = 15.0):
        self.cada_s = cada_s
        self.red: dict = {"ip": None, "wifi": None, "hotspot_iphone": False, "mensaje": "Revisando la red…"}
        self.pi: dict = {"encontrada": False, "mensaje": "Buscando la Raspberry Pi…"}
        self.hora = 0.0
        self._candado = threading.Lock()
        self._corriendo = False

    def refrescar(self, esperar: bool = False) -> None:
        with self._candado:
            if self._corriendo:
                return
            self._corriendo = True

        def trabajo():
            try:
                self.red = red()
                self.pi = probar_pi()
                self.hora = time.monotonic()
            finally:
                self._corriendo = False

        if esperar:
            trabajo()
        else:
            threading.Thread(target=trabajo, daemon=True, name="vigia-red").start()

    def estado(self) -> dict:
        if time.monotonic() - self.hora > self.cada_s:
            self.refrescar()
        return {"red": self.red, "pi": self.pi}
