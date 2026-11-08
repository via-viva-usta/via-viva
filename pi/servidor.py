"""Servidor web de la Raspberry Pi: captura en el carro (/), tablero en vivo (/tablero) y exportables.

Biblioteca estándar (http.server con hilos): nada que instalar en el celular ni en el PC, solo abrir el navegador.
Roles: editor (equipo) | alcaldia y docente (solo lectura). Ver pi/usuarios.py.

    # En la Pi (lo arranca systemd: pi/sistemas/via-viva-pi.service)
    python -m pi.servidor --fuente sensores --puerto 80 --permitir-apagado
    # Demo sin carro (Pi o PC): reproduce una grabación de phyphox o de la Pi
    python -m pi.servidor --fuente reproducir --archivo data/raw/phyphox/2026-11-07_03_pipe.zip --bucle
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
from datetime import datetime
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from pi import almacen, config, exportar
from pi.nucleo import Nucleo
from pi.sincronizacion import Sincronizador
from pi.sistema import Sistema, registrar_r7
from pi.usuarios import DURACION_SESION, Sesiones, hay_usuarios

WEB = Path(__file__).resolve().parent / "web"
mimetypes.add_type("application/javascript", ".js")
COOKIE = "vv_sesion"
LOCAL = {"usuario": "local", "nombre": "Equipo (esta máquina, sin usuarios creados)", "rol": "editor"}
LECTURA = ("editor", "alcaldia", "docente")


class App:
    """Une las piezas; el manejador HTTP solo traduce peticiones a llamadas de aquí."""

    def __init__(self, nucleo: Nucleo, fuente, calles: almacen.Calles, sincro: Sincronizador | None,
                 permitir_apagado: bool = False, url_db: str | None = None):
        self.n, self.fuente, self.calles, self.sincro = nucleo, fuente, calles, sincro
        self.sistema = Sistema()
        self.sesiones = Sesiones()
        self.permitir_apagado = permitir_apagado
        self.url_db = url_db
        self._cache: dict = {}
        self._cache_sync = (0.0, None)
        self.apagando = False
        self.version_datos = 0                    # sube con cada cambio: el tablero sabe cuándo recargar

    def con(self):
        return almacen.conectar(self.url_db)

    def leer(self, f, *args):
        con = self.con()
        try:
            return f(con, *args)
        finally:
            con.close()

    def cache(self, llave, segundos: float, f):
        hora, valor = self._cache.get(llave, (0.0, None))
        if time.monotonic() - hora > segundos or valor is None:
            valor = f()
            self._cache[llave] = (time.monotonic(), valor)
        return valor

    def cambio(self) -> None:
        self._cache.clear()
        self.version_datos += 1

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

    def vivo(self) -> dict:
        """Lo que el tablero necesita cada pocos segundos (sin la posición del carro)."""
        return {"version_datos": self.version_datos, "grabando": self.n.sesion is not None,
                "eventos_sesion": self.n.n_eventos_total, "origen": self.n.origen,
                "hora": datetime.now().astimezone().isoformat(timespec="seconds")}

    def agrupar(self, parar: threading.Event, periodo_s: float = 15.0) -> None:
        """Agrupa en huecos lo que llegue por otras vías (etl.recorridos, otra Pi) y avisa al tablero."""
        while not parar.wait(periodo_s):
            try:
                if self.leer(almacen.agrupar_huecos):
                    self.cambio()
            except Exception as err:
                self.n.aviso(f"Agrupar huecos falló: {err}")

    def apagar(self, motivo: str) -> dict:
        """Apagado seguro: cierra la grabación (fsync), deja escribir la base y apaga. Protege la microSD."""
        if self.apagando:
            return {"ok": True, "mensaje": "ya se está apagando"}
        self.apagando = True
        carpeta = self.n.detener_grabacion()
        self.n.aviso(f"Apagado seguro pedido por {motivo}")
        if not self.permitir_apagado or platform.system() != "Linux":
            self.apagando = False
            return {"ok": False, "grabacion_cerrada": carpeta,
                    "mensaje": "Grabación cerrada. El apagado del equipo solo está activo en la Pi (--permitir-apagado)."}
        if hasattr(self.fuente, "cerrar"):
            self.fuente.cerrar()
        threading.Timer(1.0, lambda: subprocess.run(["sudo", "-n", "systemctl", "poweroff"])).start()
        return {"ok": True, "grabacion_cerrada": carpeta, "mensaje": "Apagando. Espere a que el LED verde se apague."}


def crear_manejador(app: App):
    class Manejador(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        # ------------------------------------------------------------ respuestas
        def _enviar(self, codigo: int, cuerpo: bytes, tipo: str, extra: dict | None = None):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(cuerpo)

        def _json(self, obj, codigo: int = 200, extra: dict | None = None):
            self._enviar(codigo, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"),
                         "application/json; charset=utf-8", extra)

        def _archivo(self, ruta: Path):
            if not ruta.is_file():
                return self._json({"error": "no existe"}, 404)
            tipo = mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
            if ruta.suffix in (".html", ".js", ".css"):
                tipo += "; charset=utf-8"
            self._enviar(200, ruta.read_bytes(), tipo)

        def _descarga(self, datos: bytes, nombre: str, tipo: str):
            self._enviar(200, datos, tipo, {"Content-Disposition": f"attachment; filename=\"{nombre}\""})

        def _redirigir(self, destino: str):
            self._enviar(303, b"", "text/plain", {"Location": destino})

        def _cuerpo_bytes(self, maximo: int = 2_000_000) -> bytes:
            n = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(min(n, maximo)) if n else b""

        def _cuerpo(self) -> dict:
            try:
                return json.loads(self._cuerpo_bytes(65536) or b"{}")
            except json.JSONDecodeError:
                return {}

        # ------------------------------------------------------------ sesión y roles
        def _token(self) -> str | None:
            c = SimpleCookie(self.headers.get("Cookie") or "")
            return c[COOKIE].value if COOKIE in c else None

        def _local(self) -> bool:
            return self.client_address[0] in ("127.0.0.1", "::1")

        def _usuario(self) -> dict | None:
            con = app.con()
            try:
                u = app.sesiones.quien(con, self._token())
                if u is None and not hay_usuarios(con) and self._local():
                    u = LOCAL
                return u
            finally:
                con.close()

        def _exigir(self, roles, pagina: bool = False) -> dict | None:
            u = self._usuario()
            if u is not None and u["rol"] in roles:
                return u
            if pagina:
                if u is not None:                 # lectura que pide la captura → al tablero
                    self._redirigir("/tablero")
                else:
                    self._redirigir("/entrar?siguiente=" + quote(self.path))
            else:
                self._json({"error": "debe entrar" if u is None else "su rol no permite esta acción"},
                           401 if u is None else 403)
            return None

        # ------------------------------------------------------------ GET
        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            r = u.path
            sim = q.get("simulados", "1") != "0"
            try:
                if r == "/entrar":
                    return self._archivo(WEB / "entrar.html")
                if r.startswith("/static/"):
                    destino = (WEB / r[len("/static/"):]).resolve()
                    if WEB.resolve() not in destino.parents:
                        return self._json({"error": "ruta inválida"}, 403)
                    return self._archivo(destino)
                if r == "/api/yo":
                    usuario = self._usuario()
                    sin = app.leer(lambda c: not hay_usuarios(c))
                    return self._json({"usuario": usuario, "sin_usuarios": sin})
                if r in ("/", "/captura"):
                    if self._exigir(("editor",), pagina=True):
                        self._archivo(WEB / "captura.html")
                    return
                if r == "/tablero":
                    if self._exigir(LECTURA, pagina=True):
                        self._archivo(WEB / "tablero.html")
                    return
                if r == "/api/estado":
                    if self._exigir(("editor",)):
                        self._json(app.estado())
                    return
                if not self._exigir(LECTURA):
                    return
                if r == "/api/tablero/vivo":
                    return self._json(app.vivo())
                if r == "/api/tablero/huecos":
                    app.calles.listo.wait(30)
                    return self._json(app.cache(("huecos", sim), 5, lambda: {
                        "huecos": app.leer(almacen.huecos, app.calles, sim),
                        "resumen": app.leer(almacen.resumen_estados, sim)}))
                if r == "/api/tablero/riesgo":
                    app.calles.listo.wait(30)
                    llave = ("riesgo", q.get("modelo"), q.get("version"))
                    return self._json(app.cache(llave, 60, lambda: app.leer(almacen.riesgo, app.calles,
                                                                             q.get("modelo"), q.get("version"))))
                if r == "/api/tablero/peligros":
                    app.calles.listo.wait(30)
                    k = min(100, int(q.get("k", 20)))
                    return self._json(app.cache(("peligros", k), 5, lambda: app.leer(almacen.peligros, app.calles, k)))
                if r == "/api/tablero/reportes":
                    return self._json(app.leer(almacen.reportes))
                if r == "/api/tablero/historial":
                    return self._json(app.leer(almacen.historial, q["tabla"], int(q["id"])))
                if r == "/api/tablero/corredor":
                    app.calles.listo.wait(30)
                    d = app.calles.grafo.corredor(int(q["tramo"]), min(5, int(q.get("k", 2))))
                    return self._json({"tramo": int(q["tramo"]), "k": int(q.get("k", 2)),
                                       "tramos": [{"id_tramo": t, "saltos": s,
                                                   "puntos": (app.calles.info.obtener(t) or {}).get("puntos")}
                                                  for t, s in d.items()]})
                if r.startswith("/api/exportar/"):
                    return self._exportar(r.rsplit("/", 1)[1], q, sim)
                return self._json({"error": "no existe"}, 404)
            except (KeyError, ValueError) as err:
                return self._json({"error": f"parámetro inválido: {err}"}, 400)

        def _exportar(self, nombre: str, q: dict, sim: bool):
            app.calles.listo.wait(30)
            sello = datetime.now().strftime("%Y%m%d-%H%M")
            if nombre == "plantilla_reparaciones.csv":
                return self._descarga(exportar.plantilla_reparaciones(), nombre, "text/csv; charset=utf-8")
            huecos = app.leer(almacen.huecos, app.calles, sim)
            if nombre == "huecos.csv":
                return self._descarga(exportar.csv_tabla(huecos, exportar.COL_HUECOS), f"viaviva_huecos_{sello}.csv",
                                      "text/csv; charset=utf-8")
            riesgo = app.leer(almacen.riesgo, app.calles, q.get("modelo"), q.get("version"))
            if nombre == "riesgo.csv":
                filas = sorted(riesgo["tramos"], key=lambda x: -x["probabilidad"])
                return self._descarga(exportar.csv_tabla(filas, exportar.COL_RIESGO), f"viaviva_riesgo_{sello}.csv",
                                      "text/csv; charset=utf-8")
            resumen = app.leer(almacen.resumen_estados, sim)
            if nombre == "tablero.xlsx":
                peligros = app.leer(almacen.peligros, app.calles, 20)
                return self._descarga(exportar.excel(huecos, riesgo, peligros, resumen), f"viaviva_{sello}.xlsx",
                                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            if nombre == "top10.pdf":
                return self._descarga(exportar.pdf_top10(riesgo, huecos, resumen, app.calles),
                                      f"viaviva_top10_{sello}.pdf", "application/pdf")
            return self._json({"error": "exportable desconocido"}, 404)

        # ------------------------------------------------------------ POST
        def do_POST(self):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            r = u.path
            try:
                if r == "/api/entrar":
                    c = self._cuerpo()
                    con = app.con()
                    try:
                        res = app.sesiones.entrar(con, c.get("usuario", ""), c.get("clave", ""), self.client_address[0])
                    except PermissionError as err:
                        return self._json({"error": str(err)}, 429)
                    finally:
                        con.close()
                    if res is None:
                        return self._json({"error": "usuario o contraseña incorrectos"}, 401)
                    token, usuario = res
                    galleta = (f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; "
                               f"Max-Age={int(DURACION_SESION.total_seconds())}")
                    return self._json({"ok": True, "usuario": usuario}, extra={"Set-Cookie": galleta})
                if r == "/api/salir":
                    app.leer(app.sesiones.salir, self._token())
                    return self._json({"ok": True}, extra={"Set-Cookie": f"{COOKIE}=; Max-Age=0; Path=/"})
                usuario = self._exigir(("editor",))
                if usuario is None:
                    return
                if r == "/api/importar/reparaciones":
                    datos = self._cuerpo_bytes(exportar.MAX_BYTES + 1)
                    res = app.leer(exportar.importar_reparaciones, datos, usuario["usuario"], q.get("aplicar") == "1")
                    if res["aplicado"]:
                        app.cambio()
                    return self._json(res, 200 if not res["errores"] else 422)
                c = {**q, **self._cuerpo()}
                if r == "/api/grabar":
                    if c.get("accion") == "detener":
                        carpeta = app.n.detener_grabacion()
                        app.cambio()
                        return self._json({"ok": True, "carpeta": carpeta})
                    return self._json({"ok": True, "carpeta": app.n.iniciar_grabacion(c.get("nombre", ""))})
                if r == "/api/etiqueta":
                    return self._json({"ok": True, "etiqueta": app.n.etiquetar(c["clase"], origen="web")})
                if r == "/api/apagar":
                    if c.get("confirmar") != "si":
                        return self._json({"error": "falta confirmar=si"}, 400)
                    return self._json(app.apagar(f"página web ({usuario['usuario']})"))
                partes = r.strip("/").split("/")      # api/tablero/<huecos|reportes>/<id>/estado
                if len(partes) == 5 and partes[:2] == ["api", "tablero"] and partes[4] == "estado":
                    con = app.con()
                    try:
                        if partes[2] == "huecos":
                            ok = almacen.cambiar_estado_hueco(con, int(partes[3]), c["estado"], usuario["usuario"],
                                                              nota=(c.get("nota") or None))
                        elif partes[2] == "reportes":
                            ok = almacen.cambiar_estado_reporte(con, int(partes[3]), c["estado"], usuario["usuario"])
                        else:
                            return self._json({"error": "no existe"}, 404)
                    finally:
                        con.close()
                    app.cambio()
                    return self._json({"ok": ok}, 200 if ok else 404)
                return self._json({"error": "no existe"}, 404)
            except (KeyError, ValueError) as err:
                return self._json({"error": f"parámetro inválido: {err}"}, 400)

    return Manejador


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
    app_ref: list[App] = []

    def guardar(lote, nodo, org):
        almacen.guardar_eventos(lote, nodo, org, url_db)
        if app_ref:
            app_ref[0].cambio()
    nucleo = Nucleo(fuente.fs, origen=origen, id_nodo=id_nodo, dir_grabaciones=dir_grabaciones,
                    guardar_eventos=guardar, ajustar_tramo=lambda lat, lon: calles.ajustar(lat, lon, config.MAX_M_TRAMO))
    sincro = Sincronizador(url_db=url_db) if sync else None
    app = App(nucleo, fuente, calles, sincro, permitir_apagado=permitir_apagado, url_db=url_db)
    app_ref.append(app)
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
    threading.Thread(target=app.agrupar, args=(parar,), daemon=True, name="huecos").start()
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
    sin = app.leer(lambda c: not hay_usuarios(c))
    print(f"VÍA VIVA: captura http://<ip>:{a.puerto}/ · tablero http://<ip>:{a.puerto}/tablero · fuente {a.fuente}"
          + (" · SIN USUARIOS: solo responde a esta máquina (python -m pi.usuarios crear ...)" if sin else ""),
          flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        terminar()
    servidor.server_close()
    sys.exit(0)


if __name__ == "__main__":
    main()
