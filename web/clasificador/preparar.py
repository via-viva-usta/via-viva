"""Prepara y sirve la página del clasificador para probarla en el celular (iPhone) por el WiFi local.

1. Descarga UNA vez las librerías (TensorFlow.js core + backend CPU + tfjs-tflite con su WebAssembly) a vendor/.
   Después la página funciona sin internet.
2. Copia el modelo int8 elegido por dataset.modelo (dataset/salidas/<ultimo>/info.json) a modelo/.
3. Con --servir, la sirve en http://<IP del PC>:8000 para abrirla desde el celular conectado al MISMO WiFi.

Uso (desde via-viva/, cualquier Python 3.11; solo biblioteca estándar):
  python web\\clasificador\\preparar.py --servir
  python web\\clasificador\\preparar.py --version 20261105-0815-SINTETICO --servir
vendor/ y modelo/ están ignorados por Git (se regeneran con este script).
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import shutil
import socket
import socketserver
import sys
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
SALIDAS = RAIZ / "dataset" / "salidas"
LOG_LATENCIA = RAIZ / "data" / "logs" / "latencia_celular.jsonl"
CDN = "https://cdn.jsdelivr.net/npm"
LIBRERIAS = {   # versiones fijas
    "tf-core.min.js": f"{CDN}/@tensorflow/tfjs-core@4.22.0/dist/tf-core.min.js",
    "tf-backend-cpu.min.js": f"{CDN}/@tensorflow/tfjs-backend-cpu@4.22.0/dist/tf-backend-cpu.min.js",
    "tf-tflite.min.js": f"{CDN}/@tensorflow/tfjs-tflite@0.0.1-alpha.10/dist/tf-tflite.min.js",
}
WASM = ["tflite_web_api_client.js", "tflite_web_api_cc.js", "tflite_web_api_cc.wasm", "tflite_web_api_cc_simd.js",
        "tflite_web_api_cc_simd.wasm", "tflite_web_api_cc_threaded.js", "tflite_web_api_cc_threaded.wasm",
        "tflite_web_api_cc_threaded.worker.js", "tflite_web_api_cc_simd_threaded.js",
        "tflite_web_api_cc_simd_threaded.wasm", "tflite_web_api_cc_simd_threaded.worker.js"]


def descargar_vendor() -> None:
    v = AQUI / "vendor"
    v.mkdir(exist_ok=True)
    pendientes = dict(LIBRERIAS) | {w: f"{CDN}/@tensorflow/tfjs-tflite@0.0.1-alpha.10/wasm/{w}" for w in WASM}
    for nombre, url in pendientes.items():
        destino = v / nombre
        if destino.exists() and destino.stat().st_size > 0:
            continue
        print(f"  descargando {nombre}")
        with urllib.request.urlopen(url, timeout=60) as r:
            destino.write_bytes(r.read())


def copiar_modelo(version: str | None) -> dict:
    if version is None:
        ultimo = SALIDAS / "ultimo.txt"
        if not ultimo.exists():
            sys.exit("No hay modelo: correr antes dataset.modelo (ver dataset/README.md)")
        version = ultimo.read_text(encoding="utf-8").strip()
    origen = SALIDAS / version
    info = json.loads((origen / "info.json").read_text(encoding="utf-8"))
    destino = AQUI / "modelo"
    destino.mkdir(exist_ok=True)
    shutil.copy2(origen / info["tflite"], destino / "modelo.tflite")
    (destino / "info.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    return info


def ips_locales() -> list[str]:
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))          # no envía nada: solo elige la interfaz de salida
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    ips |= {i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    return sorted(i for i in ips if not i.startswith("127."))


def servir(puerto: int) -> None:
    class Manejador(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".wasm": "application/wasm"}

        def do_POST(self):                       # R7: la página manda la latencia medida en el celular
            if self.path != "/latencia":
                self.send_error(404)
                return
            datos = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 2) or b"{}")
            datos["cliente"] = self.client_address[0]
            LOG_LATENCIA.parent.mkdir(parents=True, exist_ok=True)
            with LOG_LATENCIA.open("a", encoding="utf-8") as f:
                f.write(json.dumps(datos, ensure_ascii=False) + "\n")
            print(f"Latencia en {datos['cliente']}: {datos.get('media_ms')} ± {datos.get('desv_ms')} ms (n = {datos.get('n')})")
            self.send_response(204)
            self.end_headers()

    manejador = functools.partial(Manejador, directory=str(AQUI))
    with socketserver.ThreadingTCPServer(("0.0.0.0", puerto), manejador) as srv:
        print("Abrir en el celular (mismo WiFi que el PC):")
        for ip in ips_locales():
            print(f"  http://{ip}:{puerto}/")
        print("Si no abre: permitir Python en el Firewall de Windows (red privada). Ctrl+C para cerrar.")
        srv.serve_forever()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default=None, help="versión de dataset/salidas (por defecto la última)")
    ap.add_argument("--servir", action="store_true")
    ap.add_argument("--puerto", type=int, default=8000)
    a = ap.parse_args()
    descargar_vendor()
    info = copiar_modelo(a.version)
    print(f"Modelo {info['version']} ({info['arquitectura']}, {info['variante']})"
          + ("  — SINTÉTICO: solo prueba" if info.get("sintetico") else ""))
    if a.servir:
        try:
            servir(a.puerto)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
