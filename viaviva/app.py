"""Tablero local y captura (FastAPI, decisión del 9-nov). Funciona sin internet, en el PC o en la Pi.

Páginas: /captura (equipo) · /marcar (botones grandes 1–7 para el copiloto, con PIN) · /sync (reloj y destello para el
video) · /tablero (todos los roles) · /entrar.
Roles: editor (equipo) | alcaldia y docente (solo lectura) | marcador = celular con el PIN de la captura (solo marca,
deshace y destella). Sin usuarios creados, la misma máquina (127.0.0.1) entra como editor.
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import platform
import secrets
import subprocess
import tempfile
import threading
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import Body, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from viaviva import almacen, conexion, config, exportar, sesiones
from viaviva.camara import Grabaciones
from viaviva.nucleo import Nucleo
from viaviva.sincronizacion import Sincronizador
from viaviva.sistema import Sistema
from viaviva.usuarios import DURACION_SESION, Sesiones, hay_usuarios

WEB = Path(__file__).resolve().parent / "web"
MARCA = config.RAIZ / "web" / "en_linea"        # marca.css, tema.js y fuentes de la web de Dany: un solo sistema
CALLES = WEB / "datos" / "calles_tunja.json"   # calles de Tunja (OSM) para el mapa sin internet
COOKIE, COOKIE_PIN = "vv_sesion", "vv_marcador"
LOCAL = {"usuario": "local", "nombre": "Equipo (esta máquina, sin usuarios creados)", "rol": "editor"}
LECTURA = ("editor", "alcaldia", "docente")
MARCAR = ("editor", "marcador")


class Contexto:
    """Une las piezas; las rutas solo traducen peticiones a llamadas de aquí."""

    def __init__(self, nucleo: Nucleo, fuente, calles: almacen.Calles, sincro: Sincronizador | None,
                 permitir_apagado: bool = False, url_db: str | None = None, pin: str | None = None):
        self.n, self.fuente, self.calles, self.sincro = nucleo, fuente, calles, sincro
        self.sistema = Sistema()
        self.sesiones = Sesiones()
        self.permitir_apagado = permitir_apagado
        self.url_db = url_db
        self.pin = pin or config.PIN_MARCADOR or f"{secrets.randbelow(10**6):06d}"   # se ve en la consola
        self.tokens_marcador: set[str] = set()
        self._intentos_pin: dict[str, list[float]] = {}
        self._cache: dict = {}
        self._cache_sync = (0.0, None)
        self.apagando = False
        self.version_datos = 0
        self.ip: str | None = None                # IP del equipo en la red del iPhone (la pone la CLI)
        self.simulador = None
        self.tipo_fuente = "ninguna"
        self.latido: float | None = None          # último aviso de la ventana de la app (viaviva app)
        self._muestras = (time.monotonic(), 0)    # para la frecuencia real
        self.hz_real = 0.0
        self._candado_fuente = threading.Lock()
        self.https: dict = {}                     # lo llena la CLI si arrancó el servidor HTTPS (cámara del iPhone)
        self.puerto = config.PUERTO
        self.vigia = conexion.Vigia()
        self.camara = Grabaciones()

    def con(self):
        return almacen.conectar(self.url_db)

    def medir_frecuencia(self) -> float:
        """Muestras por segundo que de verdad llegan (entre dos lecturas separadas al menos 1 s)."""
        t, n = time.monotonic(), self.n.n_acc
        t0, n0 = self._muestras
        if t - t0 >= 1.0:
            self.hz_real = round(max(0, n - n0) / (t - t0), 1) if n >= n0 else 0.0
            self._muestras = (t, n)
        return self.hz_real

    def cambiar_fuente(self, tipo: str, url: str | None = None, velocidad: float = 1.0) -> dict:
        """Cambia la fuente sin cerrar la app: phyphox (iPhone A) | ejemplo (recorrido SINTÉTICO) | ninguna."""
        if tipo not in ("phyphox", "ejemplo", "ninguna"):
            raise ValueError(f"fuente desconocida: {tipo}")
        with self._candado_fuente:
            if self.n.sesion is not None:
                raise ValueError("detenga la grabación antes de cambiar de fuente")
            if hasattr(self.fuente, "cerrar"):
                self.fuente.cerrar()
            if self.simulador:
                self.simulador.cerrar()
            if tipo == "ejemplo":
                from viaviva.ejemplo import resolver
                f, sim, origen, id_nodo = crear_fuente("replay-http", resolver("ejemplo"), velocidad, bucle=True)
            else:
                f, sim, origen, id_nodo = crear_fuente(tipo, url_phyphox=(url or config.PHYPHOX_URL))
            self.n.reiniciar_fuente(f.fs, origen, id_nodo)
            self.fuente, self.simulador, self.tipo_fuente = f, sim, tipo
            self._muestras, self.hz_real = (time.monotonic(), 0), 0.0
            f.arrancar(self.n)
            self.n.aviso({"phyphox": f"Fuente: phyphox del iPhone A ({url or config.PHYPHOX_URL})",
                          "ejemplo": "Fuente: recorrido de ejemplo SINTÉTICO por Tunja",
                          "ninguna": "Sin fuente: solo tablero"}[tipo])
            self.cambio()
            return {"ok": True, "fuente": tipo}

    def cerrar(self) -> None:
        if hasattr(self.fuente, "cerrar"):
            self.fuente.cerrar()
        if self.simulador:
            self.simulador.cerrar()

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
        e["pin"] = self.pin                       # solo lo ve el equipo (editor), para dárselo al copiloto
        e["ip"] = self.ip
        return e

    def estado_marcar(self) -> dict:
        """Lo mínimo para el celular que marca (sin trayectoria)."""
        e = self.n.estado()
        return {k: e[k] for k in ("grabando", "carpeta", "t_grabacion_s", "conectado", "acelerometro_sin_datos",
                                  "n_etiquetas", "etiquetas_por_clase", "etiquetas", "destellos", "retardo_s",
                                  "eventos", "origen")} | {"vel_kmh": e["gps"]["vel_kmh"], "gps_fix": e["gps"]["fix"]}

    def vivo(self) -> dict:
        return {"version_datos": self.version_datos, "grabando": self.n.sesion is not None,
                "eventos_sesion": self.n.n_eventos_total, "origen": self.n.origen,
                "hora": datetime.now().astimezone().isoformat(timespec="seconds")}

    def agrupar(self, parar: threading.Event, periodo_s: float = 15.0) -> None:
        while not parar.wait(periodo_s):
            try:
                if self.leer(almacen.agrupar_huecos):
                    self.cambio()
            except Exception as err:
                self.n.aviso(f"Agrupar huecos falló: {err}")

    def pin_valido(self, pin: str, ip: str) -> bool:
        ahora = time.monotonic()
        lista = [t for t in self._intentos_pin.get(ip, []) if ahora - t < 300]
        if len(lista) >= 8:
            raise PermissionError("demasiados intentos: espere 5 minutos")
        if hmac.compare_digest((pin or "").strip().encode(), self.pin.encode()):
            self._intentos_pin.pop(ip, None)
            return True
        self._intentos_pin[ip] = lista + [ahora]
        return False

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
                    "mensaje": "Grabación cerrada. Apagar el equipo solo está activo en la Pi (--permitir-apagado)."}
        if hasattr(self.fuente, "cerrar"):
            self.fuente.cerrar()
        threading.Timer(1.0, lambda: subprocess.run(["sudo", "-n", "systemctl", "poweroff"])).start()
        return {"ok": True, "grabacion_cerrada": carpeta, "mensaje": "Apagando. Espere a que el LED verde se apague."}


class Prohibido(Exception):
    def __init__(self, codigo: int, mensaje: str, pagina: bool = False, destino: str | None = None):
        self.codigo, self.mensaje, self.pagina, self.destino = codigo, mensaje, pagina, destino


def crear_app(ctx: Contexto) -> FastAPI:
    app = FastAPI(title="VÍA VIVA", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ctx = ctx
    app.mount("/static", StaticFiles(directory=WEB), name="static")

    @app.middleware("http")
    async def cabeceras(request: Request, call_next):
        r = await call_next(request)
        r.headers["Cache-Control"] = "no-store"
        r.headers["X-Content-Type-Options"] = "nosniff"
        r.headers["Referrer-Policy"] = "same-origin"
        return r

    @app.exception_handler(Prohibido)
    async def _prohibido(request: Request, e: Prohibido):
        if e.pagina:
            return RedirectResponse(e.destino or "/entrar?siguiente=" + request.url.path, status_code=303)
        return JSONResponse({"error": e.mensaje}, status_code=e.codigo)

    @app.exception_handler(ValueError)
    async def _valor(request: Request, e: ValueError):
        return JSONResponse({"error": f"parámetro inválido: {e}"}, status_code=400)

    @app.exception_handler(KeyError)
    async def _llave(request: Request, e: KeyError):
        return JSONResponse({"error": f"falta el parámetro {e}"}, status_code=400)

    # ------------------------------------------------------------ sesión y roles
    redes_editor = []
    for r in config.IPS_EDITOR:
        try:
            redes_editor.append(ipaddress.ip_network(r, strict=False))
        except ValueError:
            print(f"VIAVIVA_IPS_EDITOR: «{r}» no es una IP o red válida; se ignora", flush=True)

    def local(request: Request) -> bool:
        host = request.client.host if request.client else ""
        if host in ("127.0.0.1", "::1", "testclient"):
            return True
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            return False
        return any(ip in red for red in redes_editor)

    def usuario(request: Request) -> dict | None:
        con = ctx.con()
        try:
            u = ctx.sesiones.quien(con, request.cookies.get(COOKIE))
            if u is None and not hay_usuarios(con) and local(request):
                u = LOCAL
        finally:
            con.close()
        if u is None and request.cookies.get(COOKIE_PIN) in ctx.tokens_marcador:
            u = {"usuario": "marcador", "nombre": "Celular que marca (PIN)", "rol": "marcador"}
        return u

    def exigir(request: Request, roles, pagina: bool = False) -> dict:
        u = usuario(request)
        if u is not None and u["rol"] in roles:
            return u
        if pagina:
            if u is not None and u["rol"] in LECTURA:
                raise Prohibido(303, "", True, "/tablero")
            raise Prohibido(303, "", True, "/marcar" if "marcador" in roles else None)
        raise Prohibido(401 if u is None else 403, "debe entrar" if u is None else "su rol no permite esta acción")

    def pagina(nombre: str) -> FileResponse:
        return FileResponse(WEB / nombre, media_type="text/html; charset=utf-8")

    # ------------------------------------------------------------ páginas
    @app.get("/")
    def raiz(request: Request):
        u = usuario(request)
        if u is None:
            return RedirectResponse("/entrar", status_code=303)
        return RedirectResponse({"editor": "/captura", "marcador": "/marcar"}.get(u["rol"], "/tablero"), 303)

    @app.get("/entrar")
    def p_entrar():
        return pagina("entrar.html")

    @app.get("/captura")
    def p_captura(request: Request):
        exigir(request, ("editor",), pagina=True)
        return pagina("captura.html")

    @app.get("/marcar")
    def p_marcar():
        return pagina("marcar.html")          # la página pide el PIN si hace falta

    @app.get("/sync")
    def p_sync():
        return pagina("sync.html")

    @app.get("/tablero")
    def p_tablero(request: Request):
        exigir(request, LECTURA, pagina=True)
        return pagina("tablero.html")

    # ------------------------------------------------------------ públicas
    @app.get("/api/yo")
    def yo(request: Request):
        return {"usuario": usuario(request), "sin_usuarios": ctx.leer(lambda c: not hay_usuarios(c))}

    @app.get("/api/etiquetas")
    def etiquetas():
        return {"etiquetas": config.ETIQUETAS, "retardo_s": ctx.n.retardo_s}

    @app.get("/api/hora")
    def hora():
        return {"utc": time.time()}

    # ------------------------------------------------------------ marca compartida, app instalable y mapa sin red
    @app.get("/marca.css")
    def marca_css():
        return FileResponse(MARCA / "marca.css", media_type="text/css; charset=utf-8")

    @app.get("/tema.js")
    def tema_js():
        return FileResponse(MARCA / "tema.js", media_type="text/javascript; charset=utf-8")

    @app.get("/fuentes/{archivo}")
    def fuentes(archivo: str):
        if archivo not in ("archivo-black.woff2", "inter.woff2"):
            return JSONResponse({"error": "no existe"}, status_code=404)
        return FileResponse(MARCA / "fuentes" / archivo, media_type="font/woff2")

    @app.get("/manifest.webmanifest")
    def manifiesto():
        return FileResponse(WEB / "manifest.webmanifest", media_type="application/manifest+json")

    @app.get("/sw.js")
    def trabajador():                    # en la raíz: así puede guardar en caché toda la app y las teselas
        return FileResponse(WEB / "sw.js", media_type="text/javascript; charset=utf-8",
                            headers={"Service-Worker-Allowed": "/"})

    @app.get("/api/calles")
    def api_calles():
        """Calles de la base local (OSM ya importado); sin base, las de Tunja que trae el repositorio."""
        def armar():
            if ctx.calles.listo.wait(5) and len(ctx.calles.indice):
                tipo = {"primary": 1, "trunk": 1, "primary_link": 1, "trunk_link": 1, "secondary": 2,
                        "secondary_link": 2, "tertiary": 3, "tertiary_link": 3}
                lista = [[tipo.get(i.get("tipo_via"), 4), [[round(a, 5), round(b, 5)] for a, b in i["puntos"]]]
                         for _, i in ctx.calles.info.items()]
                return {"fuente": "base local (OpenStreetMap, ODbL)", "calles": lista}
            return {"fuente": "repositorio (OpenStreetMap, ODbL)",
                    "calles": json.loads(CALLES.read_text(encoding="utf-8"))["calles"]}
        return ctx.cache("calles", 3600, armar)

    @app.post("/api/latido")
    def latido(request: Request):
        if local(request):               # solo la ventana de la app en este PC (no los celulares)
            ctx.latido = time.monotonic()
        return {"ok": True}

    # ------------------------------------------------------------ panel de conexión
    @app.get("/api/conexion")
    def api_conexion(request: Request):
        exigir(request, ("editor",))
        vig = ctx.vigia.estado()
        ip = vig["red"].get("ip") or ctx.ip
        f = ctx.fuente
        cliente = getattr(f, "cliente", None)
        url = getattr(cliente, "url", None)
        n = ctx.n
        presente = bool(getattr(f, "ultimo_ok", None)) and getattr(f, "error", None) is None and n.conectado
        fuente = {"tipo": ctx.tipo_fuente, "url": url,
                  "puerto": (urllib.parse.urlsplit(url).port or 80) if url else None,
                  "simulador": ctx.simulador is not None, "conectado": presente if url else n.n_acc > 0,
                  "midiendo": getattr(f, "midiendo", None), "latencia_ms": getattr(f, "latencia_ms", None),
                  "hz_real": ctx.medir_frecuencia(), "hz_esperada": n.fs, "muestras": n.n_acc,
                  "reconexiones": n.reconexiones, "error": getattr(f, "error", None),
                  "grabando": n.sesion is not None}
        marcar = f"http://{ip or 'localhost'}:{ctx.puerto}/marcar"
        return {"red": vig["red"], "pi": vig["pi"], "fuente": fuente,
                "marcar": {"url": marcar, "pin": ctx.pin, "url_qr": f"{marcar}?pin={ctx.pin}"},
                "https": ctx.https, "camara": ctx.camara.estado()}

    @app.post("/api/conexion/probar")
    def api_probar(request: Request, datos: dict = Body(default={})):
        exigir(request, ("editor",))
        ctx.vigia.refrescar(esperar=True)
        url = datos.get("url") or getattr(getattr(ctx.fuente, "cliente", None), "url", None) or config.PHYPHOX_URL
        return {"phyphox": conexion.probar_phyphox(url), **ctx.vigia.estado()}

    @app.post("/api/conexion/fuente")
    def api_fuente(request: Request, datos: dict = Body(default={})):
        exigir(request, ("editor",))
        return ctx.cambiar_fuente(str(datos.get("tipo", "")), datos.get("url") or None,
                                  float(datos.get("velocidad") or 1.0))

    @app.get("/api/marcar/qr.svg")
    def api_qr(request: Request):
        exigir(request, ("editor",))
        ip = ctx.vigia.red.get("ip") or ctx.ip or "localhost"
        svg = conexion.qr_svg(f"http://{ip}:{ctx.puerto}/marcar?pin={ctx.pin}")
        if svg is None:
            return JSONResponse({"error": "falta la librería segno (pip install segno)"}, status_code=501)
        return Response(svg, media_type="image/svg+xml")

    # ------------------------------------------------------------ cámara: webcam del PC o celular (HTTPS)
    @app.get("/camara")
    def p_camara():
        return pagina("camara.html")       # pide el PIN si hace falta (igual que /marcar)

    @app.get("/ca.crt")
    def ca_crt():
        from viaviva import camara
        try:
            datos = camara.ca_der()
        except ImportError:
            return JSONResponse({"error": "falta la librería cryptography"}, status_code=501)
        return Response(datos, media_type="application/x-x509-ca-cert",
                        headers={"Content-Disposition": 'attachment; filename="VIA_VIVA_autoridad_local.crt"'})

    @app.post("/api/camara/parte")
    async def api_camara_parte(request: Request, id: str, n: int, tipo: str = "video/webm",
                               inicio: float | None = None, origen: str = "pc"):
        exigir(request, MARCAR)
        sesion = ctx.n.sesion
        if sesion is None:
            return JSONResponse({"error": "No hay grabación abierta: inicie la grabación en el PC primero"},
                                status_code=409)
        datos = await request.body()
        desfase = ctx.n.t_sesion_de_epoch(inicio) if (n == 0 and inicio) else None
        return ctx.camara.parte(sesion.carpeta, id, int(n), datos, tipo, desfase, origen[:20])

    @app.post("/api/camara/fin")
    def api_camara_fin(request: Request, id: str):
        exigir(request, MARCAR)
        r = ctx.camara.fin(id)
        ctx.cambio()
        return r

    @app.post("/api/camara/cuadro")
    async def api_camara_cuadro(request: Request, origen: str = "celular"):
        exigir(request, MARCAR)
        ctx.camara.poner_cuadro(await request.body(), origen[:20])
        return {"ok": True}

    @app.get("/api/camara/cuadro.jpg")
    def api_camara_ver(request: Request):
        exigir(request, ("editor",))
        c = ctx.camara.cuadro
        if c is None or time.time() - c[1] > 10:
            return JSONResponse({"error": "sin imagen del celular"}, status_code=404)
        return Response(c[0], media_type="image/jpeg")

    @app.post("/api/entrar")
    def entrar(request: Request, datos: dict = Body(default={})):
        con = ctx.con()
        try:
            res = ctx.sesiones.entrar(con, datos.get("usuario", ""), datos.get("clave", ""), request.client.host)
        except PermissionError as err:
            return JSONResponse({"error": str(err)}, status_code=429)
        finally:
            con.close()
        if res is None:
            return JSONResponse({"error": "usuario o contraseña incorrectos"}, status_code=401)
        token, u = res
        r = JSONResponse({"ok": True, "usuario": u})
        r.set_cookie(COOKIE, token, max_age=int(DURACION_SESION.total_seconds()), httponly=True, samesite="strict",
                     path="/")
        return r

    @app.post("/api/pin")
    def pin(request: Request, datos: dict = Body(default={})):
        try:
            ok = ctx.pin_valido(str(datos.get("pin", "")), request.client.host)
        except PermissionError as err:
            return JSONResponse({"error": str(err)}, status_code=429)
        if not ok:
            return JSONResponse({"error": "PIN incorrecto (está en la pantalla del PC de la captura)"}, status_code=401)
        token = secrets.token_urlsafe(24)
        ctx.tokens_marcador.add(token)
        r = JSONResponse({"ok": True})
        r.set_cookie(COOKIE_PIN, token, max_age=12 * 3600, httponly=True, samesite="strict", path="/")
        return r

    @app.post("/api/salir")
    def salir(request: Request):
        ctx.leer(ctx.sesiones.salir, request.cookies.get(COOKIE))
        ctx.tokens_marcador.discard(request.cookies.get(COOKIE_PIN) or "")
        r = JSONResponse({"ok": True})
        r.delete_cookie(COOKIE, path="/")
        r.delete_cookie(COOKIE_PIN, path="/")
        return r

    # ------------------------------------------------------------ captura
    @app.get("/api/estado")
    def estado(request: Request):
        exigir(request, ("editor",))
        return ctx.estado()

    @app.get("/api/marcar/estado")
    def estado_marcar(request: Request):
        exigir(request, MARCAR)
        return ctx.estado_marcar()

    @app.post("/api/etiqueta")
    def etiqueta(request: Request, datos: dict = Body(default={})):
        u = exigir(request, MARCAR)
        retardo = datos.get("retardo_s")
        e = ctx.n.etiquetar(datos["clase"], origen=datos.get("origen") or u["rol"],
                            retardo_s=None if retardo is None else float(retardo))
        return {"ok": True, "etiqueta": e}

    @app.post("/api/deshacer")
    def deshacer(request: Request):
        u = exigir(request, MARCAR)
        r = ctx.n.deshacer(origen=u["rol"])
        return {"ok": r is not None, "deshecha": r}

    @app.post("/api/destello")
    def destello(request: Request, datos: dict = Body(default={})):
        u = exigir(request, MARCAR)
        return {"ok": True, "destello": ctx.n.destello(origen=u["rol"], nota=datos.get("nota"))}

    @app.post("/api/grabar")
    def grabar(request: Request, datos: dict = Body(default={})):
        exigir(request, ("editor",))
        if datos.get("accion") == "detener":
            carpeta = ctx.n.detener_grabacion()
            ctx.cambio()
            return {"ok": True, "carpeta": carpeta}
        return {"ok": True, "carpeta": ctx.n.iniciar_grabacion(datos.get("nombre", ""))}

    @app.post("/api/apagar")
    def apagar(request: Request, datos: dict = Body(default={})):
        u = exigir(request, ("editor",))
        if datos.get("confirmar") != "si":
            return JSONResponse({"error": "falta confirmar=si"}, status_code=400)
        return ctx.apagar(f"página web ({u['usuario']})")

    # ------------------------------------------------------------ tablero (lectura)
    @app.get("/api/tablero/vivo")
    def vivo(request: Request):
        exigir(request, LECTURA)
        return ctx.vivo()

    @app.get("/api/tablero/huecos")
    def huecos(request: Request, simulados: str = "1"):
        exigir(request, LECTURA)
        ctx.calles.listo.wait(30)
        sim = simulados != "0"
        return ctx.cache(("huecos", sim), 5, lambda: {"huecos": ctx.leer(almacen.huecos, ctx.calles, sim),
                                                      "resumen": ctx.leer(almacen.resumen_estados, sim)})

    @app.get("/api/tablero/riesgo")
    def riesgo(request: Request, modelo: str | None = None, version: str | None = None):
        exigir(request, LECTURA)
        ctx.calles.listo.wait(30)
        return ctx.cache(("riesgo", modelo, version), 60,
                         lambda: ctx.leer(almacen.riesgo, ctx.calles, modelo, version))

    @app.get("/api/tablero/peligros")
    def peligros(request: Request, k: int = 20):
        exigir(request, LECTURA)
        ctx.calles.listo.wait(30)
        k = min(100, k)
        return ctx.cache(("peligros", k), 5, lambda: ctx.leer(almacen.peligros, ctx.calles, k))

    @app.get("/api/tablero/reportes")
    def reportes(request: Request):
        exigir(request, LECTURA)
        return ctx.leer(almacen.reportes)

    @app.get("/api/tablero/historial")
    def historial(request: Request, tabla: str, id: int):
        exigir(request, LECTURA)
        return ctx.leer(almacen.historial, tabla, id)

    @app.get("/api/tablero/corredor")
    def corredor(request: Request, tramo: int, k: int = 2):
        exigir(request, LECTURA)
        ctx.calles.listo.wait(30)
        d = ctx.calles.grafo.corredor(tramo, min(5, k))
        return {"tramo": tramo, "k": k, "tramos": [{"id_tramo": t, "saltos": s,
                                                    "puntos": (ctx.calles.info.obtener(t) or {}).get("puntos")}
                                                   for t, s in d.items()]}

    @app.get("/api/exportar/{nombre}")
    def exportar_archivo(request: Request, nombre: str, simulados: str = "1", modelo: str | None = None,
                         version: str | None = None):
        exigir(request, LECTURA)
        ctx.calles.listo.wait(30)
        sim = simulados != "0"
        sello = datetime.now().strftime("%Y%m%d-%H%M")

        def descarga(datos: bytes, archivo: str, tipo: str) -> Response:
            return Response(datos, media_type=tipo, headers={"Content-Disposition": f'attachment; filename="{archivo}"'})
        if nombre == "plantilla_reparaciones.csv":
            return descarga(exportar.plantilla_reparaciones(), nombre, "text/csv; charset=utf-8")
        hs = ctx.leer(almacen.huecos, ctx.calles, sim)
        if nombre == "huecos.csv":
            return descarga(exportar.csv_tabla(hs, exportar.COL_HUECOS), f"viaviva_huecos_{sello}.csv",
                            "text/csv; charset=utf-8")
        rg = ctx.leer(almacen.riesgo, ctx.calles, modelo, version)
        if nombre == "riesgo.csv":
            filas = sorted(rg["tramos"], key=lambda x: -x["probabilidad"])
            return descarga(exportar.csv_tabla(filas, exportar.COL_RIESGO), f"viaviva_riesgo_{sello}.csv",
                            "text/csv; charset=utf-8")
        resumen = ctx.leer(almacen.resumen_estados, sim)
        if nombre == "tablero.xlsx":
            pel = ctx.leer(almacen.peligros, ctx.calles, 20)
            return descarga(exportar.excel(hs, rg, pel, resumen), f"viaviva_{sello}.xlsx",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if nombre == "top10.pdf":
            return descarga(exportar.pdf_top10(rg, hs, resumen, ctx.calles), f"viaviva_top10_{sello}.pdf",
                            "application/pdf")
        return JSONResponse({"error": "exportable desconocido"}, status_code=404)

    # ------------------------------------------------------------ tablero (edición)
    @app.post("/api/tablero/{tabla}/{id_fila}/estado")
    def cambiar_estado(request: Request, tabla: str, id_fila: int, datos: dict = Body(default={})):
        u = exigir(request, ("editor",))
        con = ctx.con()
        try:
            if tabla == "huecos":
                ok = almacen.cambiar_estado_hueco(con, id_fila, datos["estado"], u["usuario"],
                                                  nota=(datos.get("nota") or None))
            elif tabla == "reportes":
                ok = almacen.cambiar_estado_reporte(con, id_fila, datos["estado"], u["usuario"])
            else:
                return JSONResponse({"error": "no existe"}, status_code=404)
        finally:
            con.close()
        ctx.cambio()
        return JSONResponse({"ok": ok}, status_code=200 if ok else 404)

    @app.post("/api/importar/reparaciones")
    async def importar(request: Request, aplicar: str = "0"):
        u = exigir(request, ("editor",))
        datos = (await request.body())[: exportar.MAX_BYTES + 1]
        res = ctx.leer(exportar.importar_reparaciones, datos, u["usuario"], aplicar == "1")
        if res["aplicado"]:
            ctx.cambio()
        return JSONResponse(res, status_code=200 if not res["errores"] else 422)

    # ------------------------------------------------------------ sesiones, video, revisión, dataset, demo
    def base_sesiones() -> Path:
        return ctx.n.dir_grabaciones

    for ruta_pag, archivo, roles in (("/sesiones", "sesiones.html", ("editor",)), ("/revision", "revision.html", ("editor",)),
                                     ("/dataset", "dataset.html", ("editor",)), ("/demo", "demo.html", ("editor",))):
        def _pagina(request: Request, archivo=archivo, roles=roles):
            exigir(request, roles, pagina=True)
            return pagina(archivo)
        app.add_api_route(ruta_pag, _pagina, methods=["GET"])

    @app.get("/api/sesiones")
    def api_sesiones(request: Request):
        exigir(request, ("editor",))
        actual = ctx.n.sesion.carpeta.name if ctx.n.sesion else None
        return {"carpeta": str(base_sesiones()), "sesiones": sesiones.listar(base_sesiones(), actual)}

    @app.get("/api/sesiones/{nombre}")
    def api_sesion(request: Request, nombre: str):
        exigir(request, ("editor",))
        return sesiones.detalle(sesiones.carpeta(base_sesiones(), nombre))

    @app.post("/api/sesiones/{nombre}/video")
    async def api_subir_video(request: Request, nombre: str, archivo: str = "video.mov"):
        exigir(request, ("editor",))
        c = sesiones.carpeta(base_sesiones(), nombre)
        ext = Path(archivo).suffix.lower()
        if ext not in sesiones.VIDEOS:
            return JSONResponse({"error": "el video debe ser .mov o .mp4"}, status_code=400)
        limite = sesiones.MAX_VIDEO_BYTES
        try:
            tam_declarado = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"error": "Content-Length inválido"}, status_code=400)
        if tam_declarado > limite:
            return JSONResponse({"error": f"video demasiado grande (máximo {limite // 1024**2} MB)"}, status_code=413)

        temporal = None
        tamano = 0
        excedido = False
        try:
            with tempfile.NamedTemporaryFile(mode="wb", prefix=".video-carga-", suffix=ext + ".tmp", dir=c,
                                             delete=False) as f:
                temporal = Path(f.name)
                async for parte in request.stream():
                    tamano += len(parte)
                    if tamano > limite:
                        excedido = True
                        break
                    f.write(parte)
                if not excedido:
                    f.flush()
            if excedido:
                temporal.unlink(missing_ok=True)
                return JSONResponse({"error": f"video demasiado grande (máximo {limite // 1024**2} MB)"},
                                    status_code=413)
            if tamano < 1000:
                temporal.unlink(missing_ok=True)
                return JSONResponse({"error": "el archivo llegó vacío"}, status_code=400)
            sello = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
            destino = c / f"video_{sello}_{uuid4().hex[:8]}{ext}"
            temporal.replace(destino)  # cambio atómico; cada intento conserva el video anterior
        except Exception:
            if temporal is not None:
                temporal.unlink(missing_ok=True)
            raise
        return await run_in_threadpool(sesiones.sincronizar_video, c, destino)

    @app.get("/api/sesiones/{nombre}/video")
    def api_video(request: Request, nombre: str):
        exigir(request, ("editor",))
        v = sesiones.ruta_video(sesiones.carpeta(base_sesiones(), nombre))
        if v is None:
            return JSONResponse({"error": "la sesión no tiene video"}, status_code=404)
        tipo = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
                ".webm": "video/webm"}[v.suffix.lower()]
        return FileResponse(v, media_type=tipo)

    @app.get("/api/sesiones/{nombre}/video/info")
    def api_video_info(request: Request, nombre: str):
        exigir(request, ("editor",))
        return sesiones.video_info(sesiones.carpeta(base_sesiones(), nombre)) or {}

    @app.post("/api/sesiones/{nombre}/video/convertir")
    def api_convertir_video(request: Request, nombre: str):
        exigir(request, ("editor",))
        return sesiones.convertir_video(sesiones.carpeta(base_sesiones(), nombre))

    @app.post("/api/sesiones/{nombre}/desfase")
    def api_desfase(request: Request, nombre: str, datos: dict = Body(default={})):
        exigir(request, ("editor",))
        return sesiones.ajustar_desfase(sesiones.carpeta(base_sesiones(), nombre), float(datos["desfase_s"]))

    @app.post("/api/sesiones/{nombre}/revision")
    def api_revisar(request: Request, nombre: str, datos: dict = Body(default={})):
        u = exigir(request, ("editor",))
        return sesiones.revisar(sesiones.carpeta(base_sesiones(), nombre), float(datos["t_s"]), datos["decision"],
                                datos.get("clase"), u["usuario"])

    @app.get("/api/dataset")
    def api_dataset(request: Request):
        exigir(request, ("editor",))
        return sesiones.estado_dataset()

    @app.post("/api/dataset/construir")
    def api_dataset_construir(request: Request):
        exigir(request, ("editor",))
        return sesiones.lanzar_dataset(base_sesiones())

    return app


def crear_fuente(fuente: str, archivo: str | None = None, velocidad: float = 1.0, bucle: bool = False,
                 url_phyphox: str = config.PHYPHOX_URL, iniciar_phyphox: bool = False):
    """(fuente, simulador | None, origen, id_nodo). fuente: phyphox | pi | replay | replay-http | ninguna."""
    simulador = None
    if fuente == "replay":
        from viaviva.fuentes import FuenteReproduccion
        f = FuenteReproduccion(Path(archivo), velocidad=velocidad, bucle=bucle)
        origen, id_nodo = "simulado", "reproduccion"
    elif fuente == "replay-http":                      # el camino completo de phyphox, contra un simulador
        from viaviva.fuente_phyphox import FuentePhyphox
        from viaviva.simulador_phyphox import SimuladorPhyphox
        simulador = SimuladorPhyphox(Path(archivo), velocidad=velocidad, bucle=bucle)
        f = FuentePhyphox(simulador.url)
        origen, id_nodo = "simulado", "reproduccion"
    elif fuente == "phyphox":
        from viaviva.fuente_phyphox import FuentePhyphox
        f = FuentePhyphox(url_phyphox, iniciar=iniciar_phyphox)
        origen, id_nodo = "phyphox", "phyphox-pc"
    elif fuente == "ninguna":
        from viaviva.fuentes import FuenteNula
        f = FuenteNula()
        origen, id_nodo = "nodo", config.ID_NODO
    else:
        from viaviva.fuentes import FuenteSensores
        f = FuenteSensores()
        origen, id_nodo = "nodo", config.ID_NODO
    return f, simulador, origen, id_nodo


def construir(fuente: str, archivo: str | None = None, velocidad: float = 1.0, bucle: bool = False,
              url_db: str | None = None, dir_grabaciones: Path | None = None, sync: bool = True,
              permitir_apagado: bool = False, url_phyphox: str = config.PHYPHOX_URL, iniciar_phyphox: bool = False,
              retardo_s: float | None = None, pin: str | None = None, resumen_al_cerrar: bool = True) -> Contexto:
    """Arma núcleo + fuente + calles + sincronización. fuente: phyphox | pi | replay | replay-http."""
    calles = almacen.Calles()
    threading.Thread(target=calles.cargar, args=(url_db,), daemon=True, name="calles").start()
    f, simulador, origen, id_nodo = crear_fuente(fuente, archivo, velocidad, bucle, url_phyphox, iniciar_phyphox)
    ref: list[Contexto] = []

    def guardar(lote, nodo, org):
        almacen.guardar_eventos(lote, nodo, org, url_db)
        if ref:
            ref[0].cambio()
    vaciar = 5.0 if fuente == "pi" else 1.0           # en la microSD se escribe con menos frecuencia
    n = Nucleo(f.fs, origen=origen, id_nodo=id_nodo, dir_grabaciones=dir_grabaciones, guardar_eventos=guardar,
               ajustar_tramo=lambda lat, lon: calles.ajustar(lat, lon, config.MAX_M_TRAMO), retardo_s=retardo_s,
               vaciar_s=vaciar)
    if resumen_al_cerrar:
        from viaviva import resumen
        n.al_cerrar_sesion = resumen.generar
    ctx = Contexto(n, f, calles, Sincronizador(url_db=url_db) if sync else None, permitir_apagado, url_db, pin)
    ctx.simulador = simulador
    ctx.tipo_fuente = "ejemplo" if archivo and "SINTETICO_ejemplo" in str(archivo) else fuente
    ref.append(ctx)
    if fuente == "pi":
        f.al_apagar = ctx.apagar
    f.arrancar(n)
    return ctx
