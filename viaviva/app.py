"""Tablero local y captura (FastAPI, decisión del 9-nov). Funciona sin internet, en el PC o en la Pi.

Páginas: /captura (equipo) · /marcar (botones grandes 1–7 para el copiloto, con PIN) · /sync (reloj y destello para el
video) · /tablero (todos los roles) · /entrar.
Roles: editor (equipo) | alcaldia y docente (solo lectura) | marcador = celular con el PIN de la captura (solo marca,
deshace y destella). Sin usuarios creados, la misma máquina (127.0.0.1) entra como editor.
"""
from __future__ import annotations

import hmac
import platform
import secrets
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from viaviva import almacen, config, exportar
from viaviva.nucleo import Nucleo
from viaviva.sincronizacion import Sincronizador
from viaviva.sistema import Sistema
from viaviva.usuarios import DURACION_SESION, Sesiones, hay_usuarios

WEB = Path(__file__).resolve().parent / "web"
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
        self.pin = pin or f"{secrets.randbelow(10**6):06d}"     # se muestra en la consola de la captura
        self.tokens_marcador: set[str] = set()
        self._intentos_pin: dict[str, list[float]] = {}
        self._cache: dict = {}
        self._cache_sync = (0.0, None)
        self.apagando = False
        self.version_datos = 0
        self.ip: str | None = None                # IP del equipo en la red del iPhone (la pone la CLI)

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
    def local(request: Request) -> bool:
        return (request.client.host if request.client else "") in ("127.0.0.1", "::1", "testclient")

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

    return app


def construir(fuente: str, archivo: str | None = None, velocidad: float = 1.0, bucle: bool = False,
              url_db: str | None = None, dir_grabaciones: Path | None = None, sync: bool = True,
              permitir_apagado: bool = False, url_phyphox: str = config.PHYPHOX_URL, iniciar_phyphox: bool = False,
              retardo_s: float | None = None, pin: str | None = None, resumen_al_cerrar: bool = True) -> Contexto:
    """Arma núcleo + fuente + calles + sincronización. fuente: phyphox | pi | replay | replay-http."""
    calles = almacen.Calles()
    threading.Thread(target=calles.cargar, args=(url_db,), daemon=True, name="calles").start()
    simulador = None
    if fuente == "replay":
        from viaviva.fuentes import FuenteReproduccion
        f = FuenteReproduccion(Path(archivo), velocidad=velocidad, bucle=bucle)
        origen, id_nodo = "simulado", "reproduccion"
    elif fuente == "replay-http":                      # el camino completo de phyphox, contra un simulador
        from viaviva.fuente_phyphox import FuentePhyphox
        from viaviva.simulador_phyphox import SimuladorPhyphox
        simulador = SimuladorPhyphox(Path(archivo), velocidad=velocidad)
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
    ref.append(ctx)
    if fuente == "pi":
        f.al_apagar = ctx.apagar
    f.arrancar(n)
    return ctx
