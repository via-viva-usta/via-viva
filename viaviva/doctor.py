"""`viaviva doctor`: pre-chequeo de una pantalla antes de cada salida. Termina en LISTO o FALTA <qué>.

Fuente phyphox (PC + iPhone): puerta de enlace (el iPhone), alcance a phyphox, buffers del experimento, flujo estable a
~100 Hz durante 5 s, GPS recibido, hora del PC, espacio en disco, batería, carpeta de sesiones, puerto del tablero e IP
para el celular que marca. Fuente pi: estado de cada sensor (todos opcionales), voltaje y temperatura.
Código de salida: 0 = LISTO, 1 = FALTA algo.
"""
from __future__ import annotations

import ctypes
import email.utils
import math
import os
import platform
import re
import shutil
import socket
import statistics
import subprocess
import time
import urllib.request
from pathlib import Path

from viaviva import config
from viaviva.fuente_phyphox import ClientePhyphox, buffers_faltantes, candidatos, filas_de

OK, AVISO, FALTA = "OK", "AVISO", "FALTA"


class Informe:
    def __init__(self):
        self.filas: list[tuple[str, str, str]] = []
        self.url_phyphox: str | None = None       # la que respondió (para dejarla en .env)

    def agregar(self, estado: str, que: str, detalle: str) -> None:
        self.filas.append((estado, que, detalle))

    @property
    def listo(self) -> bool:
        return all(e != FALTA for e, _, _ in self.filas)

    def texto(self) -> str:
        marca = {OK: "  ✔", AVISO: "  !", FALTA: "  ✘"}
        lineas = ["VÍA VIVA · doctor", "─" * 60]
        lineas += [f"{marca[e]} {q:<22} {d}" for e, q, d in self.filas]
        lineas.append("─" * 60)
        faltas = [q for e, q, _ in self.filas if e == FALTA]
        lineas.append("LISTO para salir." if not faltas else "FALTA: " + ", ".join(faltas))
        return "\n".join(lineas)

    def dict(self) -> dict:
        return {"listo": self.listo, "chequeos": [{"estado": e, "que": q, "detalle": d} for e, q, d in self.filas]}


# ---------------------------------------------------------------- utilidades del sistema
def puerta_de_enlace() -> str | None:
    try:
        if platform.system() == "Windows":
            r = subprocess.run(["powershell", "-NoProfile", "-Command",
                                "(Get-NetRoute -DestinationPrefix 0.0.0.0/0 -ErrorAction SilentlyContinue | "
                                "Sort-Object RouteMetric | Select-Object -First 1).NextHop"],
                               capture_output=True, text=True, timeout=8)
            return r.stdout.strip() or None
        if platform.system() == "Darwin":            # macOS (sin probar en Mac)
            r = subprocess.run(["route", "-n", "get", "default"], capture_output=True, text=True, timeout=3)
            linea = next((x for x in r.stdout.splitlines() if x.strip().startswith("gateway:")), "")
            return linea.split(":", 1)[1].strip() or None if linea else None
        r = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=3)
        partes = r.stdout.split()
        return partes[partes.index("via") + 1] if "via" in partes else None
    except Exception:
        return None


def ip_local() -> str | None:
    """IP de este equipo en la red del iPhone (la que abre el celular). En Docker la del contenedor no sirve: se usa
    VIAVIVA_IP_PC si está, o ninguna."""
    fija = os.getenv("VIAVIVA_IP_PC", "").strip()
    if fija:
        return fija
    if os.getenv("VIAVIVA_EN_DOCKER"):
        return None
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("172.20.10.1", 80))      # no envía nada: solo elige la interfaz de salida
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def bateria_pmset(salida: str) -> tuple[int | None, bool | None]:
    """Lee `pmset -g batt` de macOS: «Now drawing from 'AC Power'» y «-InternalBattery-0 (id=…)	85%; charging; …»."""
    m = re.search(r"(\d{1,3})%;", salida)
    if not m:
        return None, None                     # Mac de escritorio: pmset no lista batería
    return int(m.group(1)), "AC Power" in salida


def texto_firewall() -> str:
    """El aviso que pide el sistema para que un celular entre a /marcar."""
    sistema = platform.system()
    if sistema == "Windows":
        return "aceptar el aviso del Firewall de Windows en red PRIVADA"
    if sistema == "Darwin":
        return "en macOS, Permitir conexiones entrantes a Python y el acceso a la red local de Terminal"
    return "abrir el puerto en el firewall si hay uno activo"


def bateria() -> tuple[int | None, bool | None]:
    if platform.system() == "Windows":
        class Estado(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                        ("BatteryLifePercent", ctypes.c_byte), ("SystemStatusFlag", ctypes.c_byte),
                        ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
        e = Estado()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(e)):
            pct = e.BatteryLifePercent & 0xFF
            return (None if pct == 255 else pct), (None if e.ACLineStatus == 255 else e.ACLineStatus == 1)
        return None, None
    if platform.system() == "Darwin":
        try:
            salida = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            return None, None
        return bateria_pmset(salida)
    for p in Path("/sys/class/power_supply").glob("BAT*"):
        try:
            return int((p / "capacity").read_text()), (p / "status").read_text().strip() != "Discharging"
        except OSError:
            pass
    return None, None


def desfase_hora_s() -> float | None:
    """Diferencia entre la hora del PC y la de un servidor HTTP confiable (cabecera Date). None si no hay internet."""
    for url in ("https://www.google.com", "https://www.cloudflare.com"):
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "ViaViva-doctor"})
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=4) as r:
                fecha = r.headers.get("Date")
            t1 = time.time()
            if fecha:
                return (t0 + t1) / 2 - email.utils.parsedate_to_datetime(fecha).timestamp()
        except Exception:
            continue
    return None


def puerto_libre(puerto: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", puerto))
        return True
    except OSError:
        return False
    finally:
        s.close()


# ---------------------------------------------------------------- chequeos
def chequear_phyphox(inf: Informe, url: str, segundos: float = 5.0) -> None:
    cli = ClientePhyphox(url, timeout=3.0)
    cfg = cli.conectar()
    if cfg is None:
        inf.agregar(FALTA, "Alcance a phyphox", f"no responde en {' ni '.join(candidatos(url))}. ¿PC conectado al punto "
                    "de acceso del iPhone? ¿Acceso remoto activado en phyphox? Ver README_SALIDA.md")
        return
    inf.url_phyphox = cli.url
    inf.agregar(OK, "Alcance a phyphox", f"{cli.url} · experimento «{cfg.get('title', '?')}»"
                + ("" if cli.url == url.rstrip("/") else f" (detectado; se pidió {url})"))
    g = cli.grupos
    falta = buffers_faltantes(cfg, g)
    if falta:
        inf.agregar(FALTA, "Experimento", f"faltan buffers {', '.join(falta)}: abrir «VÍA VIVA 2.0» (06_CAMPO)")
    else:
        inf.agregar(OK, "Buffers", f"aceleración {'/'.join(g['acc'][1])} · ubicación {g['gps'][1][0]}/{g['gps'][1][1]} · "
                    f"giroscopio {'/'.join(v for v in g['giro'][1] if v)}")
    desde = {"acc": -1.0, "giro": -1.0, "gps": -1.0}
    try:
        primera = cli.nuevos(desde)
    except Exception as err:
        inf.agregar(FALTA, "Flujo de datos", f"error al leer: {err}")
        return
    for g in desde:
        f = filas_de(primera, g, cli.grupos)
        if f:
            desde[g] = f[-1][0]
    if not (primera.get("status") or {}).get("measuring"):
        inf.agregar(FALTA, "Flujo de datos", "phyphox está en pausa: toque ▶ en el iPhone y repita doctor")
        return
    tiempos, gps, latencias, t_fin = [], [], [], time.monotonic() + segundos
    while time.monotonic() < t_fin:
        t0 = time.perf_counter()
        try:
            r = cli.nuevos(desde)
        except Exception:
            continue
        latencias.append((time.perf_counter() - t0) * 1e3)
        acc, pos = filas_de(r, "acc", cli.grupos), filas_de(r, "gps", cli.grupos)
        if acc:
            tiempos += [f[0] for f in acc]
            desde["acc"] = acc[-1][0]
        if pos:
            gps += pos
            desde["gps"] = pos[-1][0]
        time.sleep(0.25)
    if len(tiempos) < 10:
        inf.agregar(FALTA, "Flujo de datos", f"solo {len(tiempos)} muestras en {segundos:.0f} s")
        return
    fs = (len(tiempos) - 1) / max(1e-9, tiempos[-1] - tiempos[0])
    dts = [b - a for a, b in zip(tiempos, tiempos[1:])]
    cortes = sum(1 for d in dts if d > 1.5 / config.FS_PHYPHOX_HZ)
    estado = OK if abs(fs - config.FS_PHYPHOX_HZ) <= 5 and cortes == 0 else (AVISO if fs >= 80 else FALTA)
    inf.agregar(estado, "Flujo 100 Hz", f"{fs:.1f} Hz · {cortes} cortes · petición {statistics.mean(latencias):.0f} ± "
                f"{statistics.pstdev(latencias):.0f} ms")
    fijos = [f for f in gps if not math.isnan(f[1])]
    if not fijos:
        inf.agregar(FALTA, "GPS", "sin posición: salir a cielo abierto y esperar 1–2 min")
    else:
        prec = fijos[-1][6] if len(fijos[-1]) > 6 else math.nan
        inf.agregar(OK if (math.isnan(prec) or prec <= 15) else AVISO, "GPS",
                    f"{fijos[-1][1]:.5f}, {fijos[-1][2]:.5f} · precisión {prec:.0f} m")


def chequear_pc(inf: Informe, puerto: int, dir_sesiones: Path, con_internet: bool = True) -> None:
    if con_internet:
        d = desfase_hora_s()
        if d is None:
            inf.agregar(AVISO, "Hora del sistema", "sin internet para comparar; revisar que el reloj esté en hora")
        else:
            inf.agregar(OK if abs(d) <= 2 else FALTA, "Hora del sistema",
                        f"desfase {d:+.1f} s" + ("" if abs(d) <= 2 else " → Configuración > Hora > Sincronizar ahora"))
    try:
        dir_sesiones.mkdir(parents=True, exist_ok=True)
        prueba = dir_sesiones / ".prueba_escritura"
        prueba.write_text("ok")
        prueba.unlink()
        libre = shutil.disk_usage(dir_sesiones).free / 1e9
        inf.agregar(OK if libre >= 2 else FALTA, "Disco", f"{libre:.1f} GB libres en {dir_sesiones}")
    except OSError as err:
        inf.agregar(FALTA, "Carpeta de sesiones", f"no se puede escribir en {dir_sesiones}: {err}")
    pct, enchufado = bateria()
    if pct is None:
        inf.agregar(OK, "Batería", "sin batería (equipo de escritorio o desconocido)")
    else:
        inf.agregar(FALTA if pct < 20 and not enchufado else (AVISO if pct < 50 and not enchufado else OK), "Batería",
                    f"{pct} %" + (" · cargando" if enchufado else " · sin cargador"))
    inf.agregar(OK if puerto_libre(puerto) else FALTA, "Puerto del tablero",
                f"{puerto} libre" if puerto_libre(puerto) else f"{puerto} ocupado: ¿ya hay una captura abierta?")
    ip = ip_local()
    inf.agregar(OK if ip else AVISO, "Celular que marca",
                f"http://{ip}:{puerto}/marcar (mismo WiFi; {texto_firewall()})" if ip else
                ("en Docker: http://<IP del PC>:" + str(puerto) + "/marcar (la IP con ipconfig o ifconfig; o "
                 "VIAVIVA_IP_PC)" if os.getenv("VIAVIVA_EN_DOCKER") else "sin IP en la red del iPhone"))


def chequear_pi(inf: Informe) -> None:
    from viaviva import sensores as s
    from viaviva.sistema import Sistema
    adxl = s.ADXL345()
    inf.agregar(OK if adxl.iniciar() else FALTA, "ADXL345 #1 (SPI CE0)", adxl.error or "DEVID 0xE5")
    adxl2 = s.ADXL345(cs=config.SPI_CS_ADXL2)
    inf.agregar(OK if adxl2.iniciar() else AVISO, "ADXL345 #2 (CE1)", adxl2.error or "DEVID 0xE5 (opcional)")
    try:
        from smbus2 import SMBus
        bus = SMBus(config.I2C_BUS)
    except Exception as err:
        bus = None
        inf.agregar(AVISO, "I2C", f"sin bus I2C ({err})")
    if bus is not None:
        for sensor in (s.MPU6050(bus), s.BH1750(bus)):
            inf.agregar(OK if sensor.iniciar() else AVISO, sensor.nombre, sensor.error or "responde (opcional)")
    vl = s.VL53L0X()
    inf.agregar(OK if vl.iniciar() else AVISO, "vl53l0x", vl.error or "responde (opcional)")
    gps = s.GPS()
    if gps.iniciar():
        r = None
        fin = time.monotonic() + 5
        while time.monotonic() < fin and r is None:
            try:
                r = gps.leer_linea()
            except Exception as err:
                gps.falla(err)
                break
        inf.agregar(OK if gps.lecturas else FALTA, "GPS NEO-6M", ("NMEA OK" + (" · con fijación" if gps.fix else
                    " · sin fijación aún")) if gps.lecturas else (gps.error or "sin frases NMEA"))
    else:
        inf.agregar(FALTA, "GPS NEO-6M", gps.error or "no abre /dev/serial0")
    dht = s.DHT22()
    inf.agregar(OK if dht.iniciar() else AVISO, "dht22", dht.error or "librería lista (lectura tolerante a fallos)")
    sis = Sistema().estado()
    est = sis.get("estrangulamiento") or {}
    inf.agregar(FALTA if est.get("bajo_voltaje") else (AVISO if est.get("hubo_bajo_voltaje") else OK), "Alimentación",
                "bajo voltaje: cambiar cargador o cable" if est.get("bajo_voltaje") else
                ("hubo bajo voltaje desde el arranque" if est.get("hubo_bajo_voltaje") else "sin bajo voltaje"))
    if sis.get("temp_c") is not None:
        inf.agregar(OK if sis["temp_c"] < 75 else AVISO, "Temperatura", f"{sis['temp_c']} °C")


def correr(fuente: str = "phyphox", url: str = config.PHYPHOX_URL, puerto: int = config.PUERTO,
           dir_sesiones: Path | None = None, segundos: float = 5.0, con_internet: bool = True) -> Informe:
    inf = Informe()
    if fuente == "phyphox" and ("127.0.0.1" in url or "localhost" in url):
        inf.agregar(OK, "Red", "simulador local (prueba sin iPhone)")
        chequear_phyphox(inf, url, segundos)
    elif fuente == "phyphox":
        gw = puerta_de_enlace()
        if gw:
            inf.agregar(OK, "Red", f"puerta de enlace {gw}" + ("" if gw in url else
                        f" (la URL usa {url}; si el iPhone es otro, use --url http://{gw}:8080)"))
        else:
            inf.agregar(AVISO, "Red", "sin puerta de enlace: ¿PC conectado al punto de acceso del iPhone?")
        chequear_phyphox(inf, url, segundos)
    elif fuente == "pi":
        chequear_pi(inf)
    chequear_pc(inf, puerto, Path(dir_sesiones or config.DIR_GRABACIONES), con_internet)
    return inf
