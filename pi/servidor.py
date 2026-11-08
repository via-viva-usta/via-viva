"""Servidor web de la Raspberry Pi: captura en el carro (/) y tablero de la Alcaldía (/tablero).

Biblioteca estándar (http.server con hilos): nada que instalar en el celular ni en el PC, solo abrir el navegador.

    # En la Pi (lo arranca systemd: pi/sistemas/via-viva-pi.service)
    python -m pi.servidor --fuente sensores --puerto 80 --permitir-apagado
    # Demo sin carro (Pi o PC): reproduce una grabación de phyphox o de la Pi
    python -m pi.servidor --fuente reproducir --archivo data/raw/phyphox/01.zip --bucle
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import platform
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from pi import almacen, config
from pi.nucleo import Nucleo
from pi.sincronizacion import Sincronizador
from pi.sistema import Sistema, registrar_r7

WEB = Path(__file__).resolve().parent / "web"
mimetypes.add_type("application/javascript", ".js")


class App:
    """Une las piezas; el manejador HTTP solo traduce peticiones a llamadas de aquí."""

    def __init__(self, nucleo: Nucleo, fuente, calles: almacen.Calles, sincro: Sincronizador | None,
                 permitir_apagado: bool = False, url_db: str | None = None):
        self.n, self.fuente, self.calles, self.sincro = nucleo, fuente, calles, sincro
        self.sistema = Sistema()
        self.permitir_apagado = permitir_apagado
        self.url_db = url_db
        self.clave_tablero = os.getenv("TABLERO_CLAVE", "")
        self._cache: dict = {}
        self._cache_sync = (0.0, None)
        self.apagando = False

    def con(self):
        return almacen.conectar(self.url_db)

    def cache(self, llave, segundos: float, f):
        hora, valor = self._cache.get(llave, (0.0, None))
        if time.monotonic() - hora > segundos or valor is None:
            valor = f()
            self._cache[llave] = (time.monotonic(), valor)
        return valor

    def estado(self) -> dict:
        e = self.n.estado()
        e["sistema"] = self.sistema.estado()
        hora, sync = self._cache_sync
        if self.sincro and time.monotonic() - hora > 5:
            try:
                sync = self.sincro.estado()
            except Exception as err:
                sync = {"error": str(err)}
            self._cache_sync = (time.monotonic(), sync)
        e["sincronizacion"] = sync
        e["calles"] = {"listas": self.calles.listo.is_set(), "tramos": len(self.calles.indice),
                       "error": self.calles.error}
        e["apagado_permitido"] = self.permitir_apagado
        return e

    def apagar(self, motivo: str) -> dict:
        """Apagado seguro: cierra la grabación (fsync), deja escribir la base y apaga. Protege la microSD."""
        if self.apagando:
            return {"ok": True, "mensaje": "ya se está apagando"}
        self.apagando = True
        carpeta = self.n.detener_grabacion()
        self.n.aviso(f"Apagado seguro pedido por {motivo}")
        if hasattr(self.fuente, "cerrar"):
            self.fuente.cerrar()
        if not self.permitir_apagado or platform.system() != "Linux":
            self.apagando = False
            return {"ok": False, "grabacion_cerrada": carpeta,
                    "mensaje": "Grabación cerrada. El apagado del equipo solo está activo en la Pi (--permitir-apagado)."}
        threading.Timer(1.0, lambda: subprocess.run(["sudo", "-n", "systemctl", "poweroff"])).start()
        return {"ok": True, "grabacion_cerrada": carpeta, "mensaje": "Apagando en 1 s. Espere a que el LED verde se apague."}


def crear_manejador(app: App):
    class Manejador(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, codigo: int = 200):
            cuerpo = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def _archivo(self, ruta: Path):
            if not ruta.is_file():
                return self._json({"error": "no existe"}, 404)
            datos = ruta.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", (mimetypes.guess_type(ruta.name)[0] or "application/octet-stream")
                             + ("; charset=utf-8" if ruta.suffix in (".html", ".js", ".css") else ""))
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

        def _cuerpo(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            try:
                return json.loads(self.rfile.read(min(n, 65536)) or b"{}")
            except json.JSONDecodeError:
                return {}

        def _local(self) -> bool:
            return self.client_address[0] in ("127.0.0.1", "::1")

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            r = u.path
            try:
                if r in ("/", "/captura"):
                    return self._archivo(WEB / "captura.html")
                if r == "/tablero":
                    return self._archivo(WEB / "tablero.html")
                if r.startswith("/static/"):
                    destino = (WEB / r[len("/static/"):]).resolve()
                    if WEB.resolve() not in destino.parents:
                        return self._json({"error": "ruta inválida"}, 403)
                    return self._archivo(destino)
                if r == "/api/estado":
                    return self._json(app.estado())
                if r == "/api/tablero/riesgo":
                    app.calles.listo.wait(30)
                    llave = ("riesgo", q.get("modelo"), q.get("version"))
                    return self._json(app.cache(llave, 60, lambda: _con(app, almacen.riesgo, app.calles,
                                                                         q.get("modelo"), q.get("version"))))
                if r == "/api/tablero/peligros":
                    app.calles.listo.wait(30)
                    k = min(100, int(q.get("k", 20)))
                    return self._json(app.cache(("peligros", k), 10, lambda: _con(app, almacen.peligros, app.calles, k)))
                if r == "/api/tablero/reportes":
                    return self._json(_con(app, almacen.reportes))
                if r == "/api/tablero/corredor":
                    app.calles.listo.wait(30)
                    d = app.calles.grafo.corredor(int(q["tramo"]), min(5, int(q.get("k", 2))))
                    return self._json({"tramo": int(q["tramo"]), "k": int(q.get("k", 2)),
                                       "tramos": [{"id_tramo": t, "saltos": s,
                                                   "puntos": (app.calles.info.obtener(t) or {}).get("puntos")}
                                                  for t, s in d.items()]})
                return self._json({"error": "no existe"}, 404)
            except (KeyError, ValueError) as err:
                return self._json({"error": f"parámetro inválido: {err}"}, 400)

        def do_POST(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            c = {**q, **self._cuerpo()}
            r = u.path
            try:
                if r == "/api/grabar":
                    if c.get("accion") == "detener":
                        return self._json({"ok": True, "carpeta": app.n.detener_grabacion()})
                    return self._json({"ok": True, "carpeta": app.n.iniciar_grabacion(c.get("nombre", ""))})
                if r == "/api/etiqueta":
                    return self._json({"ok": True, "etiqueta": app.n.etiquetar(c["clase"], origen="web")})
                if r == "/api/apagar":
                    if c.get("confirmar") != "si":
                        return self._json({"error": "falta confirmar=si"}, 400)
                    return self._json(app.apagar("página web"))
                if r.startswith("/api/tablero/reportes/") and r.endswith("/estado"):
                    # Cambiar el estado de un reporte: con TABLERO_CLAVE de .env, o solo desde la misma máquina.
                    permitido = (almacen.clave_valida(self.headers.get("X-Clave"), app.clave_tablero)
                                 if app.clave_tablero else self._local())
                    if not permitido:
                        return self._json({"error": "sin permiso: falta la clave del tablero"}, 403)
                    id_rep = int(r.split("/")[4])
                    con = app.con()
                    try:
                        ok = almacen.cambiar_estado(con, id_rep, c["estado"])
                    finally:
                        con.close()
                    app._cache.clear()
                    return self._json({"ok": ok}, 200 if ok else 404)
                return self._json({"error": "no existe"}, 404)
            except (KeyError, ValueError) as err:
                return self._json({"error": f"parámetro inválido: {err}"}, 400)

    return Manejador


def _con(app: App, f, *args):
    con = app.con()
    try:
        return f(con, *args)
    finally:
        con.close()


def construir(fuente_tipo: str, archivo: str | None = None, velocidad: float = 1.0, bucle: bool = False,
              url_db: str | None = None, dir_grabaciones: Path | None = None, sync: bool = True,
              permitir_apagado: bool = False):
    """Arma núcleo + fuente + calles + sincronización (también lo usan las pruebas)."""
    calles = almacen.Calles()
    threading.Thread(target=calles.cargar, args=(url_db,), daemon=True, name="calles").start()
    if fuente_tipo == "reproducir":
        from pi.fuentes import FuenteReproduccion
        fuente = FuenteReproduccion(Path(archivo), velocidad=velocidad, bucle=bucle)
        origen, id_nodo = "simulado", "reproduccion"
    else:
        from pi.fuentes import FuenteSensores
        fuente = FuenteSensores()
        origen, id_nodo = "nodo", config.ID_NODO
    nucleo = Nucleo(fuente.fs, origen=origen, id_nodo=id_nodo, dir_grabaciones=dir_grabaciones,
                    guardar_eventos=lambda lote, nodo, org: almacen.guardar_eventos(lote, nodo, org, url_db),
                    ajustar_tramo=lambda lat, lon: calles.ajustar(lat, lon, config.MAX_M_TRAMO))
    sincro = Sincronizador(url_db=url_db) if sync else None
    app = App(nucleo, fuente, calles, sincro, permitir_apagado=permitir_apagado, url_db=url_db)
    if fuente_tipo != "reproducir":
        fuente.al_apagar = app.apagar
    fuente.arrancar(nucleo)
    return app


def main():
    ap = argparse.ArgumentParser(description="Servidor VÍA VIVA en la Raspberry Pi (captura + tablero)")
    ap.add_argument("--fuente", choices=["sensores", "reproducir"], default="sensores")
    ap.add_argument("--archivo", help="grabación a reproducir (zip o carpeta de phyphox o de la Pi)")
    ap.add_argument("--velocidad", type=float, default=1.0)
    ap.add_argument("--bucle", action="store_true", help="repetir la grabación sin fin (demo)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--puerto", type=int, default=config.PUERTO)
    ap.add_argument("--grabar-al-arrancar", action="store_true", help="empieza a grabar sin tocar la página")
    ap.add_argument("--sin-sync", action="store_true", help="no sincronizar con la nube")
    ap.add_argument("--permitir-apagado", action="store_true", help="el pulsador y la web pueden apagar la Pi")
    a = ap.parse_args()
    if a.fuente == "reproducir" and not a.archivo:
        ap.error("--fuente reproducir necesita --archivo")

    app = construir(a.fuente, a.archivo, a.velocidad, a.bucle, sync=not a.sin_sync,
                    permitir_apagado=a.permitir_apagado)
    parar = threading.Event()
    threading.Thread(target=registrar_r7, args=(app.n, app.sistema, parar), daemon=True, name="r7").start()
    if app.sincro:
        threading.Thread(target=app.sincro.bucle, args=(parar,), daemon=True, name="sincronizacion").start()
    if a.grabar_al_arrancar:
        app.n.iniciar_grabacion("auto")
    servidor = ThreadingHTTPServer((a.host, a.puerto), crear_manejador(app))
    servidor.daemon_threads = True

    def terminar(*_):                      # systemd manda SIGTERM al detener o apagar: cerrar archivos bien
        parar.set()
        app.n.detener_grabacion()
        threading.Thread(target=servidor.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, terminar)
    print(f"VÍA VIVA Pi: captura en http://<ip>:{a.puerto}/  ·  tablero en http://<ip>:{a.puerto}/tablero"
          f"  ·  fuente: {a.fuente}", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        terminar()
    servidor.server_close()
    sys.exit(0)


if __name__ == "__main__":
    main()
