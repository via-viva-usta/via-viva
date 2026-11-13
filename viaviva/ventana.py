"""`viaviva app`: la aplicación en su propia ventana (lo que abre el icono VÍA VIVA del escritorio).

Decisión (12-nov): ventana de **Edge o Chrome en modo aplicación** (`--app=`), no pywebview ni Electron.
- Windows 10/11 ya traen Edge: no hay que instalar nada más (pywebview pide pythonnet + WebView2 y Electron ~150 MB).
- Es el mismo motor que el navegador: cámara (getUserMedia en localhost), descargas de PDF/Excel, arrastrar el video,
  imprimir y la caché del mapa funcionan igual que en las pruebas.
- Perfil propio (`data/app_ventana/`): no toca el Edge de la persona y la ventana se puede seguir como un proceso.
Si no hay Edge ni Chrome (p. ej. un Mac solo con Safari) se abre el navegador normal: funciona igual, en una pestaña.

Ciclo de vida: este proceso levanta el servidor, abre la ventana y espera. Al cerrarla (o si la ventana deja de dar
señales 20 s) cierra la grabación abierta (RESUMEN incluido), detiene la fuente y termina. Si ya hay una app corriendo
en el puerto, solo abre otra ventana hacia ella.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from viaviva import config

PERFIL = config.RAIZ / "data" / "app_ventana"
LOG = config.RAIZ / "data" / "logs" / "app.log"


def _log_si_no_hay_consola() -> None:
    """Con pythonw (el icono) no hay consola: lo que se imprima va a data/logs/app.log."""
    if sys.stdout is None or sys.stderr is None:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        f = open(LOG, "a", encoding="utf-8", buffering=1)      # noqa: SIM115 (queda abierto mientras viva la app)
        sys.stdout = sys.stdout or f
        sys.stderr = sys.stderr or f
        print(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} viaviva app", flush=True)


def navegador_app() -> str | None:
    """Edge o Chrome (los que tienen modo --app)."""
    sistema = platform.system()
    if sistema == "Windows":
        bases = [os.getenv("PROGRAMFILES(X86)"), os.getenv("PROGRAMFILES"), os.getenv("LOCALAPPDATA")]
        rel = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
        for r in rel:
            for b in bases:
                if b and Path(b, r).exists():
                    return str(Path(b, r))
        return shutil.which("msedge") or shutil.which("chrome")
    if sistema == "Darwin":
        for r in ("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
            if Path(r).exists():
                return r
        return None
    for n in ("microsoft-edge", "google-chrome", "chromium", "chromium-browser"):
        if shutil.which(n):
            return shutil.which(n)
    return None


def abrir_ventana(url: str, exe: str | None = None) -> subprocess.Popen | None:
    exe = exe or navegador_app()
    if not exe:
        webbrowser.open(url)
        return None
    PERFIL.mkdir(parents=True, exist_ok=True)
    args = [exe, f"--app={url}", f"--user-data-dir={PERFIL}", "--no-first-run", "--no-default-browser-check",
            "--window-size=1440,900", "--hide-crash-restore-bubble"]
    extra = {"creationflags": 0x08000000} if platform.system() == "Windows" else {}
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **extra)


def _responde(puerto: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/hora", timeout=1) as r:
            return "utc" in json.loads(r.read().decode("utf-8"))
    except Exception:
        return False


def main(a) -> int:
    _log_si_no_hay_consola()
    puerto = a.puerto
    url = f"http://localhost:{puerto}/captura?app=1"
    if _responde(puerto):                     # ya hay una app abierta: otra ventana hacia la misma
        if not a.sin_ventana:
            abrir_ventana(url)
        print(f"La app ya estaba abierta en el puerto {puerto}: se abrió otra ventana.")
        return 0
    from viaviva import doctor
    if not doctor.puerto_libre(puerto):
        puerto = next((p for p in range(puerto + 1, puerto + 20) if doctor.puerto_libre(p)), puerto)
        url = f"http://localhost:{puerto}/captura?app=1"

    import uvicorn

    from viaviva.app import construir, crear_app
    from viaviva.cli import arrancar_https
    from viaviva.sistema import registrar_r7
    fuente = a.fuente or os.getenv("VIAVIVA_FUENTE_APP", "phyphox")
    ctx = construir("ninguna", sync=True)
    ctx.puerto = puerto
    ctx.ip = doctor.ip_local()
    ctx.actualizacion_habilitada = platform.system() in ("Windows", "Darwin")
    if fuente != "ninguna":
        ctx.cambiar_fuente(fuente)
    parar = threading.Event()
    threading.Thread(target=registrar_r7, args=(ctx.n, ctx.sistema, parar), daemon=True, name="r7").start()
    threading.Thread(target=ctx.agrupar, args=(parar,), daemon=True, name="huecos").start()
    if ctx.sincro:
        threading.Thread(target=ctx.sincro.bucle, args=(parar,), daemon=True, name="sincronizacion").start()
    app = crear_app(ctx)
    servidor = uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=puerto, log_level="warning"))
    hilo = threading.Thread(target=servidor.run, daemon=True, name="servidor")
    hilo.start()
    seguro = None if a.sin_https else arrancar_https(ctx, app, "0.0.0.0", a.puerto_https)
    for _ in range(100):
        if _responde(puerto):
            break
        time.sleep(0.1)
    print(f"VÍA VIVA en {url} · fuente {fuente} · sesiones en {ctx.n.dir_grabaciones}", flush=True)
    ventana = None if a.sin_ventana else abrir_ventana(url)
    inicio = time.monotonic()
    reiniciar = False
    try:
        while hilo.is_alive():
            time.sleep(1.0)
            if ctx.reinicio_pendiente.is_set():
                print("Actualización lista; cerrando esta versión para reiniciar.", flush=True)
                reiniciar = True
                break
            if a.sin_ventana:
                continue
            ahora = time.monotonic()
            if ventana is not None and ventana.poll() is not None:
                print("Ventana cerrada.", flush=True)
                break
            if ctx.latido is not None and ahora - ctx.latido > 20:
                print("La ventana dejó de responder 20 s: se cierra la app.", flush=True)
                break
            if ctx.latido is None and ventana is None and ahora - inicio > 180:
                print("Ninguna ventana se conectó en 3 min: se cierra la app.", flush=True)
                break
    except KeyboardInterrupt:
        pass
    finally:
        carpeta = ctx.n.detener_grabacion()
        if carpeta:
            print(f"Grabación guardada: {ctx.n.dir_grabaciones / carpeta}", flush=True)
        parar.set()
        ctx.cerrar()
        servidor.should_exit = True
        if seguro:
            seguro.should_exit = True
        if ventana is not None and ventana.poll() is None:
            ventana.terminate()
        hilo.join(10)
    if reiniciar:
        from viaviva import doctor
        limite = time.monotonic() + 12
        while time.monotonic() < limite and not doctor.puerto_libre(puerto):
            time.sleep(0.25)
        if not doctor.puerto_libre(puerto):
            print("La actualización quedó instalada, pero el puerto sigue ocupado. Cierra el proceso anterior y abre VÍA VIVA.",
                  flush=True)
            return 1
        args = [sys.executable, "-m", "viaviva", "app", "--puerto", str(puerto),
                "--puerto-https", str(getattr(a, "puerto_https", 8443))]
        tipo = ctx.tipo_fuente if ctx.tipo_fuente in ("phyphox", "ejemplo", "ninguna") else fuente
        if tipo:
            args.extend(("--fuente", tipo))
        if getattr(a, "sin_https", False):
            args.append("--sin-https")
        if getattr(a, "sin_ventana", False):
            args.append("--sin-ventana")
        opciones = {"cwd": config.RAIZ}
        if platform.system() == "Windows":
            opciones["creationflags"] = 0x08000000
        subprocess.Popen(args, **opciones)
        print("VÍA VIVA se está abriendo de nuevo con la versión instalada.", flush=True)
    return 0
