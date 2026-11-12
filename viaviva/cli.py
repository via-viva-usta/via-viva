"""`viaviva` — un solo comando para todo (en Windows: `viaviva.cmd` en la raíz del repo).

    viaviva doctor                         pre-chequeo antes de salir (LISTO / FALTA X)
    viaviva capture                        captura con phyphox (iPhone de punto de acceso) + tablero en :8000
    viaviva capture --replay <export.zip>  reproduce una grabación como si fuera en vivo (sin carro)
    viaviva capture --source pi            sensores de la Raspberry Pi
    viaviva serve                          solo el tablero local (sin captura)
    viaviva resumen <carpeta|export>       RESUMEN.md de una sesión
    viaviva detector ... | dataset ...     detector calibrable y constructor del dataset (Fase B)
    viaviva usuarios ... | sync ...        usuarios y roles; sincronización con Supabase
    viaviva r7 ...                         informe de recursos
"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path

from viaviva import config


def _doctor(a) -> int:
    from viaviva import doctor
    fuente = "pi" if a.source == "pi" else "phyphox"
    url = a.url
    sim = None
    if a.simulado:                        # prueba del doctor sin iPhone: simulador con un export
        from viaviva.ejemplo import resolver
        from viaviva.simulador_phyphox import SimuladorPhyphox
        sim = SimuladorPhyphox(Path(resolver(a.simulado)))
        url = sim.url
    inf = doctor.correr(fuente, url, a.puerto, segundos=a.segundos, con_internet=not a.sin_internet)
    if sim:
        sim.cerrar()
    elif fuente == "phyphox" and inf.url_phyphox and not a.no_guardar and inf.url_phyphox != config.PHYPHOX_URL:
        try:
            config.guardar_env("VIAVIVA_PHYPHOX_URL", inf.url_phyphox)
            print(f"URL de phyphox guardada en .env: {inf.url_phyphox}")
        except OSError:                    # p. ej. en Docker (/app es de solo lectura para el usuario)
            print(f"phyphox respondió en {inf.url_phyphox}: úsela con VIAVIVA_PHYPHOX_URL={inf.url_phyphox}")
    if a.json:
        import json
        print(json.dumps(inf.dict(), ensure_ascii=False, indent=1))
    else:
        print(inf.texto())
    return 0 if inf.listo else 1


def _teclado(ctx, parar: threading.Event) -> None:
    """Teclas en la consola de Windows: 1–7 marcan, U deshace, S destello, Q termina."""
    try:
        import msvcrt
    except ImportError:
        return
    teclas = {t: c for t, c, _ in config.ETIQUETAS}
    while not parar.is_set():
        if not msvcrt.kbhit():
            parar.wait(0.05)
            continue
        k = msvcrt.getwch().lower()
        try:
            if k in teclas:
                e = ctx.n.etiquetar(teclas[k], origen="teclado")
                print(f"  ✓ {e['clase']} (t = {e['t_s']} s, {e['vel_kmh']} km/h)", flush=True)
            elif k == "u":
                r = ctx.n.deshacer(origen="teclado")
                print(f"  ↶ deshecha: {r['clase']}" if r else "  (nada para deshacer)", flush=True)
            elif k == "s":
                d = ctx.n.destello(origen="teclado")
                print(f"  ⏱ marca de sincronía {d['utc']}", flush=True)
            elif k == "q":
                print("  Terminando…", flush=True)
                parar.set()
        except Exception as err:
            print(f"  ✘ {err}", flush=True)


def _servir(ctx, a, grabar: bool) -> int:
    import uvicorn

    from viaviva import doctor
    from viaviva.app import crear_app
    from viaviva.sistema import registrar_r7
    ctx.ip = doctor.ip_local()
    parar = threading.Event()
    threading.Thread(target=registrar_r7, args=(ctx.n, ctx.sistema, parar), daemon=True, name="r7").start()
    threading.Thread(target=ctx.agrupar, args=(parar,), daemon=True, name="huecos").start()
    if ctx.sincro:
        threading.Thread(target=ctx.sincro.bucle, args=(parar,), daemon=True, name="sincronizacion").start()
    if grabar:
        ctx.n.iniciar_grabacion(getattr(a, "nombre", "") or "")
    servidor = uvicorn.Server(uvicorn.Config(crear_app(ctx), host=a.host, port=a.puerto, log_level="warning"))
    url_local = f"http://localhost:{a.puerto}"
    print("═" * 64)
    print(f" VÍA VIVA · fuente: {getattr(a, 'source', 'ninguna')} · carpeta: {ctx.n.dir_grabaciones}")
    if grabar:
        print(f" Grabando: {ctx.n.sesion.carpeta.name if ctx.n.sesion else '—'}")
    print(f" Captura: {url_local}/captura    Tablero: {url_local}/tablero    Sincronía: {url_local}/sync")
    ip = ctx.ip or "<IP de este PC>"          # en Docker la IP del contenedor no sirve al celular
    print(f" Celular extra (opcional): http://{ip}:{a.puerto}/marcar    PIN: {ctx.pin}")
    if sys.platform == "win32":
        print(" Teclas aquí: 1 hueco · 2 resalto · 3 grieta · 4 parche · 5 tapa · 6 obstáculo · 7 vía buena ·")
        print("              U deshacer · S marca de sincronía · Q terminar (o Ctrl+C)")
    else:                                     # Mac, Linux y Docker: las teclas de la consola son solo de Windows
        print(" Marcar: teclas 1–7 y U en la página /captura (o un celular en /marcar). Terminar: Ctrl+C")
    print("═" * 64, flush=True)
    if getattr(a, "abrir", False):
        threading.Timer(1.5, lambda: webbrowser.open(f"{url_local}/captura")).start()
    threading.Thread(target=_teclado, args=(ctx, parar), daemon=True, name="teclado").start()

    def vigilar():
        parar.wait()
        servidor.should_exit = True
    threading.Thread(target=vigilar, daemon=True).start()
    try:
        servidor.run()
    except KeyboardInterrupt:                 # Ctrl+C en Mac/Linux: uvicorn lo vuelve a lanzar al cerrar; no es un error
        pass
    finally:
        parar.set()
        carpeta = ctx.n.detener_grabacion()
        if hasattr(ctx.fuente, "cerrar"):
            ctx.fuente.cerrar()
        if getattr(ctx, "simulador", None):
            ctx.simulador.cerrar()
        if carpeta:
            ruta = ctx.n.dir_grabaciones / carpeta
            print(f"\nSesión guardada: {ruta}\nResumen: {ruta / 'RESUMEN.md'}")
            resumen = ruta / "RESUMEN.md"
            if resumen.exists():
                print(resumen.read_text(encoding="utf-8"))
    return 0


def _capture(a) -> int:
    from viaviva.app import construir
    from viaviva.ejemplo import resolver
    a.replay = resolver(a.replay)          # «ejemplo» = export SINTÉTICO de práctica (cualquier PC)
    fuente = a.source
    if a.replay:
        fuente = "replay-http" if a.por_http else "replay"
    if fuente == "replay" and not a.replay:
        print("--source replay necesita --replay <archivo>", file=sys.stderr)
        return 2
    ctx = construir(fuente, archivo=a.replay, velocidad=a.velocidad, bucle=a.bucle, sync=not a.sin_sync,
                    permitir_apagado=a.permitir_apagado, url_phyphox=a.url, iniciar_phyphox=a.iniciar_phyphox,
                    retardo_s=a.retardo, dir_grabaciones=Path(a.salida) if a.salida else None)
    return _servir(ctx, a, grabar=not a.sin_grabar)


def _serve(a) -> int:
    from viaviva.app import construir
    ctx = construir("ninguna", sync=not a.sin_sync, resumen_al_cerrar=False)
    return _servir(ctx, a, grabar=False)


def _resumen(a) -> int:
    from viaviva import resumen
    r = resumen.generar(Path(a.carpeta))
    print(resumen.markdown(r))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("usuarios", "sync", "detector", "dataset", "r7", "modelo", "nube"):   # delegar a cada módulo
        cmd, resto = argv[0], argv[1:]
        modulo = {"usuarios": "viaviva.usuarios", "sync": "viaviva.sincronizacion", "detector": "viaviva.detector",
                  "dataset": "viaviva.ventanas", "r7": "viaviva.r7.medir", "modelo": "viaviva.modelo_ventanas",
                  "nube": "viaviva.nube"}[cmd]
        import importlib
        sys.argv = [f"viaviva {cmd}", *resto]
        return importlib.import_module(modulo).main() or 0

    ap = argparse.ArgumentParser(prog="viaviva", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("doctor", help="pre-chequeo antes de salir")
    d.add_argument("--source", choices=["phyphox", "pi"], default="phyphox")
    d.add_argument("--url", default=config.PHYPHOX_URL)
    d.add_argument("--puerto", type=int, default=config.PUERTO)
    d.add_argument("--segundos", type=float, default=5.0)
    d.add_argument("--sin-internet", action="store_true", help="no comparar la hora con internet")
    d.add_argument("--simulado", metavar="EXPORT", help="probar contra un simulador de phyphox con este export")
    d.add_argument("--no-guardar", action="store_true", help="no dejar en .env la URL de phyphox detectada")
    d.add_argument("--json", action="store_true")
    c = sub.add_parser("capture", help="captura + tablero local")
    c.add_argument("--source", choices=["phyphox", "pi", "replay"], default="phyphox")
    c.add_argument("--url", default=config.PHYPHOX_URL, help="acceso remoto de phyphox")
    c.add_argument("--replay", metavar="ARCHIVO", help="export de phyphox o sesión a reproducir")
    c.add_argument("--por-http", action="store_true", help="reproducir a través de un simulador de phyphox (prueba "
                                                           "el camino completo, con reconexión)")
    c.add_argument("--velocidad", type=float, default=1.0)
    c.add_argument("--bucle", action="store_true")
    c.add_argument("--nombre", default="", help="se agrega al nombre de la carpeta de la sesión")
    c.add_argument("--salida", help="carpeta de sesiones (por defecto 06_CAMPO/sesiones)")
    c.add_argument("--retardo", type=float, default=None, help=f"retardo de reacción (s), por defecto "
                                                               f"{config.RETARDO_REACCION_S}")
    c.add_argument("--sin-grabar", action="store_true", help="no empezar a grabar sola")
    c.add_argument("--iniciar-phyphox", action="store_true", help="enviar ▶ a phyphox al empezar")
    c.add_argument("--host", default="0.0.0.0")
    c.add_argument("--puerto", type=int, default=config.PUERTO)
    c.add_argument("--sin-sync", action="store_true")
    c.add_argument("--permitir-apagado", action="store_true")
    c.add_argument("--abrir", action="store_true", help="abrir el navegador")
    s = sub.add_parser("serve", help="solo el tablero local")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--puerto", type=int, default=config.PUERTO)
    s.add_argument("--sin-sync", action="store_true")
    s.add_argument("--abrir", action="store_true")
    r = sub.add_parser("resumen", help="RESUMEN.md de una sesión o export")
    r.add_argument("carpeta")
    sub.add_parser("usuarios", help="python -m viaviva usuarios crear <u> --rol editor|alcaldia|docente")
    sub.add_parser("sync", help="sincronización con Supabase (--una-vez)")
    sub.add_parser("detector", help="detector calibrable (Fase B)")
    sub.add_parser("dataset", help="constructor del dataset (Fase B)")
    sub.add_parser("r7", help="informe de recursos")
    sub.add_parser("modelo", help="esqueleto TFLite del clasificador de ventanas")
    sub.add_parser("nube", help="preparar el tablero en línea (config.js + tramos.geojson)")
    a = ap.parse_args(argv)
    return {"doctor": _doctor, "capture": _capture, "serve": _serve, "resumen": _resumen}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
