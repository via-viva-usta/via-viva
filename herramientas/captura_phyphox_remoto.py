"""Captura EN VIVO desde phyphox (iPhone) por el "Acceso remoto", con etiquetas por teclado y vista en vivo.

Qué hace:
  1. Cada ~0,5 s pide por HTTP los datos nuevos del experimento "VÍA VIVA 2.0" (buffers accX/Y/Z + acc_time,
     gyroX/Y/Z + gyro_time, gpsLat/Lon/Z/V/Dir/Accuracy/ZAccuracy + gps_time) y los guarda en una carpeta con el MISMO
     formato que el export de phyphox en iOS (Accelerometer.csv "Time (s)","X (m/s^2)"…, Gyroscope.csv, Location.csv,
     meta/time.csv): validar_campo y etl.recorridos la leen sin cambios.
  2. Si se corta la conexión, avisa (pitido + mensaje), reintenta solo y sigue donde iba (no se pierden datos: phyphox
     los guarda y se piden desde el último tiempo recibido). Si phyphox se reinicia, abre una carpeta "_parte2".
  3. Etiquetas en vivo con el teclado del PC: H hueco · R resalto · G grieta · T tapa · O obstáculo · I impacto fuerte ·
     P parada (inicio/fin) · Q terminar. Guarda hora del PC, tiempo del experimento y posición GPS actual en
     <carpeta>/etiquetas.csv y, para etl.recorridos, <carpeta>_etiquetas.csv (t_s,clase). El cronómetro por vueltas
     (analysis/vueltas_a_etiquetas.py) queda como plan B.
  4. Vista en vivo en el navegador del PC (http://127.0.0.1:8090): velocidad, aceleración vertical, posición en el mapa,
     contador de eventos del detector por umbrales (la misma regla del nodo) y botones para etiquetar.
  5. --reproducir EXPORT: un simulador de phyphox sirve una grabación (zip o carpeta) al mismo flujo, para la demo sin
     carro; --simular EXPORT solo levanta el simulador (para probar desde otro PC).

En el iPhone: phyphox → experimento "VÍA VIVA 2.0" → menú ⋮ → "Permitir acceso remoto": muestra la URL (con el iPhone
como punto de acceso suele ser http://172.20.10.1:8080 — VERIFICAR la que muestra phyphox). El PC se conecta al punto de
acceso del iPhone. Iniciar la medición con ▶ en phyphox (o con --iniciar).

Uso (desde via-viva/):
  dataset\\.venv\\Scripts\\python -m herramientas.captura_phyphox_remoto --url http://172.20.10.1:8080 --nombre ruta1_pipe
  dataset\\.venv\\Scripts\\python -m herramientas.captura_phyphox_remoto --reproducir data\\raw\\phyphox\\2026-11-07_03_pipe.zip --velocidad 5
Los datos quedan en data/raw/phyphox/ (captura) o data/raw/reproducciones/ (reproducción): ignorados por Git.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from analysis.detector_umbral import ParametrosUmbral

RAIZ = Path(__file__).resolve().parent.parent
G = 9.81
INTERVALO_S = 0.5
GRUPOS = {   # buffers del experimento "VÍA VIVA 2.0" (06_CAMPO/*.phyphox) → archivo y encabezado del export de iOS
    "acc": {"tiempo": "acc_time", "valores": ["accX", "accY", "accZ"], "archivo": "Accelerometer.csv",
            "encabezado": ["Time (s)", "X (m/s^2)", "Y (m/s^2)", "Z (m/s^2)"]},
    "giro": {"tiempo": "gyro_time", "valores": ["gyroX", "gyroY", "gyroZ"], "archivo": "Gyroscope.csv",
             "encabezado": ["Time (s)", "X (rad/s)", "Y (rad/s)", "Z (rad/s)"]},
    "gps": {"tiempo": "gps_time", "valores": ["gpsLat", "gpsLon", "gpsZ", "gpsV", "gpsDir", "gpsAccuracy", "gpsZAccuracy"],
            "archivo": "Location.csv",
            "encabezado": ["Time (s)", "Latitude (°)", "Longitude (°)", "Height (m)", "Velocity (m/s)", "Direction (°)",
                           "Horizontal Accuracy (m)", "Vertical Accuracy (°)"]},   # así, con (°), lo escribe phyphox iOS
}
TECLAS = {"h": "hueco", "r": "resalto", "g": "grieta", "t": "tapa", "o": "obstaculo", "i": "impacto_fuerte"}


def _num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return math.nan


def _fmt(v: float) -> str:
    return "NaN" if math.isnan(v) else f"{v:.9E}"          # igual que phyphox: 3.912016662E-2


# ---------------------------------------------------------------- cliente del acceso remoto
class Cliente:
    def __init__(self, url: str, timeout: float = 2.0):
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
        """Datos con tiempo > desde[grupo], para todos los grupos, en UNA petición."""
        partes = []
        for g, d in GRUPOS.items():
            t0 = repr(desde[g])
            partes.append(f"{d['tiempo']}={t0}")
            partes += [f"{v}={t0}|{d['tiempo']}" for v in d["valores"]]
        return self._json("/get?" + "&".join(partes))


def revisar_buffers(cfg: dict) -> list[str]:
    """Nombres de buffer que faltan en el experimento del celular (vacío = todo bien)."""
    hay = {b["name"] if isinstance(b, dict) else str(b) for b in cfg.get("buffers", [])}
    pedidos = {n for d in GRUPOS.values() for n in [d["tiempo"], *d["valores"]]}
    return sorted(pedidos - hay) if hay else []


# ---------------------------------------------------------------- detector por umbrales en flujo (misma regla del nodo)
class DetectorEnVivo:
    """Versión muestra a muestra de analysis/detector_umbral.detectar_umbral (mismos parámetros y resultado)."""

    def __init__(self, fs: float, p: ParametrosUmbral | None = None):
        self.p = p or ParametrosUmbral()
        self.n_p2p = int(min(64, max(2, round(self.p.ventana_p2p_s * fs))))
        self.alfa = 1.0 / (self.p.tau_base_s * fs)
        self.calentamiento = int(self.p.tau_base_s * fs)
        self.refractario = int(self.p.refractario_s * fs)
        self.ventana = deque(maxlen=self.n_p2p)
        self.ms2, self.n, self.ultimo = 0.0, 0, None

    def muestra(self, a_g: float, vel_kmh: float) -> float | None:
        """Devuelve el pico a pico (g) si dispara en esta muestra."""
        self.ventana.append(a_g)
        p2p = max(self.ventana) - min(self.ventana)
        rms_ant = math.sqrt(self.ms2)
        disparo = (self.n >= self.calentamiento and vel_kmh > self.p.v_min_kmh and p2p > self.p.k_rel * rms_ant
                   and p2p > self.p.p2p_min_g and (self.ultimo is None or self.n - self.ultimo >= self.refractario))
        if disparo:
            self.ultimo = self.n
        self.ms2 += self.alfa * (a_g * a_g - self.ms2)
        self.n += 1
        return p2p if disparo else None


# ---------------------------------------------------------------- captura
class Captura:
    def __init__(self, carpeta: Path, fs_supuesta: float = 100.0):
        self.base = carpeta
        self.carpeta = carpeta
        self.parte = 1
        self.candado = threading.Lock()
        self.desde = {g: -1.0 for g in GRUPOS}
        self.archivos: dict[str, io.TextIOBase] = {}
        self.det = DetectorEnVivo(fs_supuesta)
        self.ultimo_t_acc, self.mono_ultimo, self.inicio_epoch = 0.0, time.monotonic(), None
        self.vel_kmh, self.lat, self.lon, self.precision = 0.0, math.nan, math.nan, math.nan
        self.serie = deque(maxlen=600)          # (t, a_vert) a ~20 Hz: 30 s
        self.trayecto = deque(maxlen=3000)      # (lat, lon)
        self.eventos, self.etiquetas = [], []
        self.n_acc, self.conectado, self.reconexiones, self.midiendo = 0, False, 0, False
        self.parada_abierta = False
        self.mensajes = deque(maxlen=8)
        self._abrir()

    # --- archivos
    def _abrir(self):
        self.carpeta.mkdir(parents=True, exist_ok=True)
        (self.carpeta / "meta").mkdir(exist_ok=True)
        for g, d in GRUPOS.items():
            f = open(self.carpeta / d["archivo"], "w", encoding="utf-8", newline="")
            f.write(",".join(f'"{c}"' for c in d["encabezado"]) + "\n")
            self.archivos[g] = f
        self.f_etq = open(self.carpeta / "etiquetas.csv", "w", encoding="utf-8", newline="")
        csv.writer(self.f_etq).writerow(["t_s", "hora_pc", "clase", "lat", "lon", "vel_kmh", "origen"])
        self.f_etq_corto = open(self.carpeta.parent / f"{self.carpeta.name}_etiquetas.csv", "w", encoding="utf-8",
                                newline="")
        csv.writer(self.f_etq_corto).writerow(["t_s", "clase"])

    def _meta_tiempo(self):
        if self.inicio_epoch is None:
            return
        texto = datetime.fromtimestamp(self.inicio_epoch).astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " UTC-05:00"
        (self.carpeta / "meta" / "time.csv").write_text(
            '"event","experiment time","system time","system time text"\n'
            f'"START",{0.0:.15E},{self.inicio_epoch:.6f},"{texto}"\n', encoding="utf-8")

    def nueva_parte(self):
        """phyphox se reinició (otra sesión): los tiempos vuelven a 0, así que se abre otra carpeta."""
        self.cerrar()
        self.parte += 1
        self.carpeta = self.base.with_name(f"{self.base.name}_parte{self.parte}")
        self.desde = {g: -1.0 for g in GRUPOS}
        self.inicio_epoch = None
        self._abrir()
        self.aviso(f"phyphox empezó una medición nueva: se guarda en {self.carpeta.name}")

    def cerrar(self):
        for f in [*self.archivos.values(), self.f_etq, self.f_etq_corto]:
            f.close()

    def aviso(self, texto: str):
        self.mensajes.append(f"{datetime.now():%H:%M:%S} {texto}")
        print(f"\n[{datetime.now():%H:%M:%S}] {texto}", flush=True)

    # --- datos nuevos
    def recibir(self, resp: dict):
        buf = resp.get("buffer", {})
        with self.candado:
            for g, d in GRUPOS.items():
                cols = [buf.get(n, {}).get("buffer", []) for n in [d["tiempo"], *d["valores"]]]
                n = min(len(c) for c in cols)
                if n == 0:
                    continue
                filas = list(zip(*(c[:n] for c in cols)))
                f = self.archivos[g]
                for fila in filas:
                    f.write(",".join(_fmt(_num(v)) for v in fila) + "\n")
                f.flush()
                self.desde[g] = _num(filas[-1][0])
                getattr(self, f"_procesar_{g}")([[_num(v) for v in fila] for fila in filas])

    def _procesar_acc(self, filas):
        if self.inicio_epoch is None:
            self.inicio_epoch = time.time() - filas[-1][0]   # tiempo 0 del experimento en la hora del PC
            self._meta_tiempo()
        for k, (t, x, y, z) in enumerate(filas):
            a = math.sqrt(x * x + y * y + z * z) / G - 1.0
            p2p = self.det.muestra(a, self.vel_kmh)
            if p2p is not None:
                self.eventos.append({"t_s": round(t, 2), "p2p_g": round(p2p, 3), "lat": self.lat, "lon": self.lon,
                                     "vel_kmh": round(self.vel_kmh, 1)})
            if (self.n_acc + k) % 5 == 0:               # 100 Hz → 20 Hz para la gráfica
                self.serie.append((round(t, 2), round(a, 3)))
        self.n_acc += len(filas)
        self.ultimo_t_acc, self.mono_ultimo = filas[-1][0], time.monotonic()

    def _procesar_giro(self, filas):
        pass

    def _procesar_gps(self, filas):
        for t, lat, lon, _, v, _, prec, _ in filas:
            if not math.isnan(lat) and not math.isnan(lon):
                self.lat, self.lon, self.precision = lat, lon, prec
                self.trayecto.append((round(lat, 6), round(lon, 6)))
            self.vel_kmh = 0.0 if math.isnan(v) or v < 0 else v * 3.6

    # --- etiquetas
    def t_ahora(self) -> float:
        """Tiempo del experimento AHORA: último tiempo recibido + lo que pasó desde entonces en el PC."""
        return self.ultimo_t_acc + (time.monotonic() - self.mono_ultimo if self.midiendo else 0.0)

    def etiquetar(self, clase: str, origen: str = "teclado") -> dict:
        if clase == "parada":
            clase = "parada_fin" if self.parada_abierta else "parada_inicio"
            self.parada_abierta = not self.parada_abierta
        with self.candado:
            e = {"t_s": round(self.t_ahora(), 2), "hora_pc": datetime.now().astimezone().isoformat(timespec="milliseconds"),
                 "clase": clase, "lat": self.lat, "lon": self.lon, "vel_kmh": round(self.vel_kmh, 1), "origen": origen}
            csv.writer(self.f_etq).writerow(e.values())
            csv.writer(self.f_etq_corto).writerow([e["t_s"], clase])
            self.f_etq.flush()
            self.f_etq_corto.flush()
            self.etiquetas.append(e)
        print(f"\n  ✓ {clase} en t = {e['t_s']} s ({self.vel_kmh:.0f} km/h)", flush=True)
        return e

    def estado(self) -> dict:
        with self.candado:
            return {"conectado": self.conectado, "midiendo": self.midiendo, "t_s": round(self.t_ahora(), 1),
                    "vel_kmh": round(self.vel_kmh, 1), "lat": None if math.isnan(self.lat) else self.lat,
                    "lon": None if math.isnan(self.lon) else self.lon,
                    "precision_m": None if math.isnan(self.precision) else round(self.precision, 1),
                    "muestras": self.n_acc, "eventos": len(self.eventos), "etiquetas": self.etiquetas[-8:],
                    "n_etiquetas": len(self.etiquetas), "ultimos_eventos": self.eventos[-5:],
                    "serie": list(self.serie), "trayecto": list(self.trayecto)[::3],
                    "reconexiones": self.reconexiones, "mensajes": list(self.mensajes), "carpeta": self.carpeta.name}


def bucle(cliente: Cliente, cap: Captura, parar: threading.Event, iniciar: bool = False, fin_al_parar: bool = False):
    """Pide datos cada INTERVALO_S; si se corta, avisa y reintenta sin perder lo ya guardado."""
    sesion, corte, avisado = None, None, False
    try:
        faltan = revisar_buffers(cliente.config())
        if faltan:
            cap.aviso(f"ATENCIÓN: el experimento del celular no tiene los buffers {faltan}: usar 'VÍA VIVA 2.0'")
        if iniciar:
            cliente.control("start")
    except (urllib.error.URLError, OSError, ValueError) as e:
        cap.aviso(f"No responde {cliente.url} ({e}). ¿Acceso remoto activado y PC en el punto de acceso del iPhone?")
    visto_midiendo = False
    while not parar.is_set():
        t0 = time.monotonic()
        try:
            resp = cliente.nuevos(cap.desde)
            st = resp.get("status", {})
            if sesion is not None and st.get("session") not in (None, sesion):
                cap.nueva_parte()
            sesion = st.get("session", sesion)
            cap.midiendo = bool(st.get("measuring", True))
            visto_midiendo |= cap.midiendo
            cap.recibir(resp)
            if not cap.conectado:
                if corte is not None:
                    cap.reconexiones += 1
                    cap.aviso(f"Reconectado tras {time.monotonic() - corte:.0f} s; se siguió desde t = {cap.desde['acc']:.1f} s")
                cap.conectado, corte, avisado = True, None, False
            if fin_al_parar and visto_midiendo and not cap.midiendo:
                cap.recibir(cliente.nuevos(cap.desde))       # lo último que quedaba
                break
        except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
            if cap.conectado or not avisado:
                corte = corte or time.monotonic()
                print("\a", end="")
                cap.aviso(f"CONEXIÓN PERDIDA con phyphox ({type(e).__name__}). Reintentando… (los datos siguen en el celular)")
                avisado = True
            cap.conectado = False
        parar.wait(max(0.05, INTERVALO_S - (time.monotonic() - t0)))


# ---------------------------------------------------------------- simulador de phyphox (modo reproducir)
def leer_export(ruta: Path) -> dict[str, list[list[float]]]:
    """{grupo: filas} de un export de phyphox (zip o carpeta) en el formato de iOS."""
    def abrir(nombre):
        if ruta.is_dir():
            p = ruta / nombre
            return p.read_text(encoding="utf-8-sig") if p.exists() else None
        with zipfile.ZipFile(ruta) as z:
            return z.read(nombre).decode("utf-8-sig") if nombre in z.namelist() else None
    datos = {}
    for g, d in GRUPOS.items():
        texto = abrir(d["archivo"])
        filas = [] if texto is None else [[_num(v) for v in f] for f in list(csv.reader(io.StringIO(texto)))[1:] if f]
        ancho = len(d["encabezado"])
        datos[g] = [f + [math.nan] * (ancho - len(f)) for f in filas]
    return datos


class SimuladorPhyphox:
    """Imita el acceso remoto de phyphox (/config, /get, /control) sirviendo una grabación en tiempo (acelerado)."""

    def __init__(self, ruta: Path, velocidad: float = 1.0, puerto: int = 0, host: str = "127.0.0.1"):
        self.datos = leer_export(ruta)
        self.velocidad = velocidad
        self.fin = max((f[-1][0] for f in self.datos.values() if f), default=0.0)
        self.t0 = time.monotonic()
        self.pausado = False                     # para probar cortes de conexión
        sim = self

        class Manejador(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if sim.pausado:
                    self.close_connection = True
                    return                        # no responde: el cliente ve un corte
                u = urllib.parse.urlsplit(self.path)
                if u.path == "/config":
                    cuerpo = {"title": "VÍA VIVA 2.0 (reproducción)", "buffers": [
                        {"name": n, "size": 0} for d in GRUPOS.values() for n in [d["tiempo"], *d["valores"]]]}
                elif u.path == "/get":
                    cuerpo = sim.responder(urllib.parse.unquote(u.query))
                elif u.path == "/control":
                    cuerpo = {"result": True}
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                b = json.dumps(cuerpo, allow_nan=False, default=str).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

        self.servidor = ThreadingHTTPServer((host, puerto), Manejador)
        self.url = f"http://{host}:{self.servidor.server_address[1]}"
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def ahora(self) -> float:
        return (time.monotonic() - self.t0) * self.velocidad

    def responder(self, consulta: str) -> dict:
        t_ahora = min(self.ahora(), self.fin)
        indice = {}
        for g, d in GRUPOS.items():
            indice[d["tiempo"]] = (g, 0)
            for k, v in enumerate(d["valores"], 1):
                indice[v] = (g, k)
        salida = {}
        for par in consulta.split("&"):
            nombre, _, arg = par.partition("=")
            if nombre not in indice:
                continue
            g, col = indice[nombre]
            umbral = _num(arg.split("|")[0]) if arg and arg != "full" else -math.inf
            vals = [f[col] for f in self.datos[g] if umbral < f[0] <= t_ahora]
            salida[nombre] = {"size": 0, "updateMode": "partial", "buffer": [None if math.isnan(v) else v for v in vals]}
        return {"buffer": salida, "status": {"session": "reproduccion", "measuring": self.ahora() <= self.fin,
                                            "timedRun": False, "countDown": 0}}

    def cerrar(self):
        self.servidor.shutdown()


# ---------------------------------------------------------------- vista en vivo (navegador del PC)
PAGINA = (Path(__file__).resolve().parent / "vista_en_vivo.html")


def servir_vista(cap: Captura, puerto: int, host: str = "127.0.0.1") -> ThreadingHTTPServer:
    class Manejador(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _enviar(self, codigo, cuerpo: bytes, tipo):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cuerpo)

        def do_GET(self):
            if self.path.startswith("/estado"):
                self._enviar(200, json.dumps(cap.estado(), default=lambda v: None).encode(), "application/json")
            else:
                self._enviar(200, PAGINA.read_bytes(), "text/html; charset=utf-8")

        def do_POST(self):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            clase = q.get("clase", [""])[0]
            if clase in [*TECLAS.values(), "parada"]:
                self._enviar(200, json.dumps(cap.etiquetar(clase, "pagina"), default=lambda v: None).encode(),
                             "application/json")
            else:
                self._enviar(400, b'{"error":"clase"}', "application/json")

    srv = ThreadingHTTPServer((host, puerto), Manejador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def teclado(cap: Captura, parar: threading.Event):
    """Teclas del PC (consola de Windows, sin Enter). En otros sistemas: letra + Enter."""
    try:
        import msvcrt
    except ImportError:
        msvcrt = None
    while not parar.is_set():
        if msvcrt is not None:
            if not msvcrt.kbhit():
                time.sleep(0.03)
                continue
            k = msvcrt.getwch().lower()
        else:
            linea = sys.stdin.readline()
            if not linea:
                return
            k = linea.strip().lower()[:1]
        if k == "q":
            parar.set()
        elif k == "p":
            cap.etiquetar("parada")
        elif k in TECLAS:
            cap.etiquetar(TECLAS[k])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://172.20.10.1:8080", help="URL que muestra phyphox en 'acceso remoto'")
    ap.add_argument("--nombre", default=None, help="nombre del recorrido (p. ej. ruta1_pipe); se antepone la fecha")
    ap.add_argument("--salida", type=Path, default=None, help="carpeta base (data/raw/phyphox o data/raw/reproducciones)")
    ap.add_argument("--iniciar", action="store_true", help="oprimir ▶ en phyphox desde el PC")
    ap.add_argument("--reproducir", type=Path, default=None, help="export (zip o carpeta) a reproducir como si fuera en vivo")
    ap.add_argument("--simular", type=Path, default=None, help="solo levantar el simulador de phyphox con este export")
    ap.add_argument("--velocidad", type=float, default=1.0, help="×N en la reproducción (1 = tiempo real)")
    ap.add_argument("--puerto-vista", type=int, default=8090)
    ap.add_argument("--sin-vista", action="store_true")
    ap.add_argument("--sin-teclado", action="store_true")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    if a.simular:
        sim = SimuladorPhyphox(a.simular, a.velocidad, puerto=8080, host="0.0.0.0")
        print(f"Simulador de phyphox con {a.simular.name} en {sim.url} (×{a.velocidad}). Ctrl+C para cerrar.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return

    sim = SimuladorPhyphox(a.reproducir, a.velocidad) if a.reproducir else None
    url = sim.url if sim else a.url
    base = a.salida or RAIZ / "data" / "raw" / ("reproducciones" if sim else "phyphox")
    nombre = a.nombre or (f"REPRODUCCION_{a.reproducir.stem}" if sim else "captura")
    carpeta = base / f"{datetime.now():%Y-%m-%d_%H-%M-%S}_{nombre}"
    cap = Captura(carpeta)
    parar = threading.Event()
    vista = None if a.sin_vista else servir_vista(cap, a.puerto_vista)
    print(f"Fuente: {'REPRODUCCIÓN de ' + a.reproducir.name if sim else url} → {carpeta}")
    if vista:
        print(f"Vista en vivo: http://127.0.0.1:{a.puerto_vista}/")
    print("Teclas: H hueco · R resalto · G grieta · T tapa · O obstáculo · I impacto · P parada · Q terminar")
    if not a.sin_teclado:
        threading.Thread(target=teclado, args=(cap, parar), daemon=True).start()
    hilo = threading.Thread(target=bucle, args=(Cliente(url), cap, parar, a.iniciar, sim is not None), daemon=True)
    hilo.start()
    try:
        while hilo.is_alive():
            e = cap.estado()
            print(f"\r{'EN LÍNEA ' if e['conectado'] else 'SIN CONEXIÓN'} t={e['t_s']:7.1f} s · {e['vel_kmh']:4.0f} km/h · "
                  f"GPS ±{e['precision_m'] or 0:3.0f} m · muestras {e['muestras']:6d} · eventos {e['eventos']:3d} · "
                  f"etiquetas {e['n_etiquetas']:3d}   ", end="", flush=True)
            hilo.join(1.0)
    except KeyboardInterrupt:
        parar.set()
        hilo.join(3)
    cap.cerrar()
    if sim:
        sim.cerrar()
    if vista:
        vista.shutdown()
    print(f"\nGuardado en {cap.carpeta} ({cap.n_acc} muestras, {len(cap.eventos)} eventos, {len(cap.etiquetas)} etiquetas)."
          f"\nRevisar: dataset\\.venv\\Scripts\\python -m herramientas.validar_campo --phyphox {cap.carpeta.parent}")


if __name__ == "__main__":
    main()
