"""Imita el acceso remoto de phyphox (/config, /get, /control) sirviendo una grabación en tiempo real (o acelerado).

Sirve para probar la captura de extremo a extremo SIN salir: `viaviva capture --replay <export> --por-http` levanta este
simulador y la captura lo lee igual que al iPhone. También lo usa `viaviva doctor --simulado` y las pruebas.
`pausado = True` deja de responder (simula que se cayó el hotspot).
"""
from __future__ import annotations

import bisect
import json
import math
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from viaviva.fuente_phyphox import FUENTES, GRUPOS, SALIDAS
from viaviva.fuentes import _leer_tabla

ARCHIVO = {"acc": ("Accelerometer.csv", 4), "giro": ("Gyroscope.csv", 4), "gps": ("Location.csv", 8)}


class SimuladorPhyphox:
    def __init__(self, ruta: Path, velocidad: float = 1.0, puerto: int = 0, host: str = "127.0.0.1",
                 grupos: dict | None = None):
        self.grupos = grupos or GRUPOS
        self.datos = {}
        for g, (nombre, ancho) in ARCHIVO.items():
            filas = [f[:ancho] + [math.nan] * (ancho - len(f)) for f in _leer_tabla(Path(ruta), nombre)]
            self.datos[g] = (filas, [f[0] for f in filas])
        if not self.datos["acc"][0]:
            raise ValueError(f"{ruta}: sin Accelerometer.csv")
        self.velocidad = velocidad
        self.fin = max((f[-1][0] for f, _ in self.datos.values() if f), default=0.0)
        self.t0 = time.monotonic()
        self.pausado = False
        self.peticiones = 0
        sim = self

        class Manejador(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                if sim.pausado:
                    self.close_connection = True
                    return
                u = urllib.parse.urlsplit(self.path)
                if u.path == "/config":
                    cuerpo = {"title": "VÍA VIVA 2.0 (simulado)", "buffers": [
                        {"name": n, "size": 0} for t, vs in sim.grupos.values() for n in [t, *vs]],
                        "inputs": [{"source": FUENTES[g][0], "outputs": [{"t": t}, *({k: v} for k, v in
                                                                                   zip(SALIDAS[g], vs))]}
                                   for g, (t, vs) in sim.grupos.items()]}
                elif u.path == "/get":
                    sim.peticiones += 1
                    cuerpo = sim.responder(urllib.parse.unquote(u.query))
                elif u.path == "/control":
                    cuerpo = {"result": True}
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                b = json.dumps(cuerpo, allow_nan=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

        self.servidor = ThreadingHTTPServer((host, puerto), Manejador)
        self.servidor.daemon_threads = True
        self.url = f"http://{host}:{self.servidor.server_address[1]}"
        threading.Thread(target=self.servidor.serve_forever, daemon=True).start()

    def ahora(self) -> float:
        return (time.monotonic() - self.t0) * self.velocidad

    def responder(self, consulta: str) -> dict:
        t_ahora = min(self.ahora(), self.fin)
        indice = {}
        for g, (tiempo, valores) in self.grupos.items():
            indice[tiempo] = (g, 0)
            for k, v in enumerate(valores, 1):
                indice[v] = (g, k)
        salida = {}
        for par in consulta.split("&"):
            nombre, _, arg = par.partition("=")
            if nombre not in indice:
                continue
            g, col = indice[nombre]
            filas, tiempos = self.datos[g]
            try:
                umbral = float(arg.split("|")[0]) if arg and arg != "full" else -math.inf
            except ValueError:
                umbral = -math.inf
            i0, i1 = bisect.bisect_right(tiempos, umbral), bisect.bisect_right(tiempos, t_ahora)
            vals = [filas[i][col] if col < len(filas[i]) else math.nan for i in range(i0, i1)]
            salida[nombre] = {"size": 0, "updateMode": "partial",
                              "buffer": [None if (v is None or math.isnan(v)) else v for v in vals]}
        return {"buffer": salida, "status": {"session": "simulado", "measuring": self.ahora() <= self.fin,
                                            "timedRun": False, "countDown": 0}}

    def cerrar(self) -> None:
        self.servidor.shutdown()
