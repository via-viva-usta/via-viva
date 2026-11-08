"""Benchmark de la MISMA CNN int8 de fotos en cualquier equipo (PC, Raspberry Pi 4, …) para la comparación de R7.

Mide, con la versión de dataset/salidas/ultimo.txt (o --modelo):
  * latencia de 100 inferencias (5 de calentamiento no cuentan): media ± desviación (Welford), mín, máx;
  * RAM: memoria residente del proceso antes y después de cargar el modelo (pico, si el sistema lo da);
  * memoria mínima de activaciones (cota inferior de la "arena" de TFLite Micro) = el mayor par entrada+salida de
    una operación, y si el modelo CABE en el ESP32 (520 KB de SRAM, ~300 KB libres con el firmware; 4 MB de flash);
  * consumo (opcional): con --corriente-ma y --voltaje leídos del tester USB → energía por inferencia (mJ).
Guarda una línea JSON en data/logs/benchmark_cnn.jsonl (ignorada por Git) y la imprime.

Uso:
  PC (control):   futuro\\bot\\.venv\\Scripts\\python pi\\r7\\benchmark_cnn.py
  Raspberry Pi:   pi/.venv/bin/python -m pip install numpy ai-edge-litert   (una vez)
                  pi/.venv/bin/python pi/r7/benchmark_cnn.py --equipo "Pi 4 <RAM>" --corriente-ma 650 --voltaje 5.1
Necesita numpy y ai-edge-litert (o TensorFlow). El modelo (dataset/salidas/<versión>/) no está en Git: copiarlo del PC.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[2]
SALIDAS = RAIZ / "dataset" / "salidas"
LOG = RAIZ / "data" / "logs" / "benchmark_cnn.jsonl"
ESP32_SRAM_LIBRE_B = 300_000        # ~heap libre con el firmware del nodo (medir con la fila MEM heap_libre_B)
ESP32_FLASH_APP_LIBRE_B = 1_966_080 - 944_585   # partición min_spiffs menos el firmware actual (pio run, 7-nov)


def interprete(ruta: Path):
    try:
        from ai_edge_litert.interpreter import Interpreter, OpResolverType
        motor = "LiteRT"
    except ImportError:
        from tensorflow.lite import Interpreter
        from tensorflow.lite.experimental import OpResolverType
        motor = "tensorflow.lite"
    try:
        it = Interpreter(model_path=str(ruta), num_threads=os.cpu_count())
        it.allocate_tensors()
        return it, motor + " + XNNPACK"
    except RuntimeError:   # MobileNetV3 int8: XNNPACK no lo prepara → núcleos de referencia (mucho más lentos)
        it = Interpreter(model_path=str(ruta), num_threads=os.cpu_count(),
                         experimental_op_resolver_type=OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES)
        it.allocate_tensors()
        return it, motor + " (sin XNNPACK)"


def memoria_rss_mb() -> tuple[float, float | None]:
    """(RSS actual, pico) en MB. psutil si está; en Linux/macOS, resource da el pico."""
    actual = pico = None
    try:
        import psutil
        actual = psutil.Process().memory_info().rss / 2**20
    except ImportError:
        pass
    try:
        import resource
        r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        pico = r / 2**20 if sys.platform == "darwin" else r / 1024
        actual = actual or pico
    except ImportError:
        pass
    return actual or math.nan, pico


def activaciones_minimas(it) -> int:
    """Cota inferior de memoria de trabajo: el mayor (entradas + salidas) de tensores NO constantes de una operación."""
    tam = {t["index"]: int(np.prod(t["shape"])) * np.dtype(t["dtype"]).itemsize for t in it.get_tensor_details()}
    ops = it._get_ops_details()                       # API interna, estable en TFLite/LiteRT
    producidos = {o for op in ops for o in op["outputs"]} | {d["index"] for d in it.get_input_details()}
    return max(sum(tam[i] for i in [*op["inputs"], *op["outputs"]] if i in producidos and i >= 0) for op in ops)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modelo", type=Path, default=None, help=".tflite (por defecto el de dataset/salidas/ultimo.txt)")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--equipo", default=f"{platform.node()} ({platform.machine()})")
    ap.add_argument("--corriente-ma", type=float, default=None, help="corriente promedio durante la prueba (tester USB)")
    ap.add_argument("--voltaje", type=float, default=5.0)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    info = {}
    ruta = a.modelo
    if ruta is None:
        version = (SALIDAS / "ultimo.txt").read_text(encoding="utf-8").strip()
        info = json.loads((SALIDAS / version / "info.json").read_text(encoding="utf-8"))
        ruta = SALIDAS / version / info["tflite"]
    rss0, _ = memoria_rss_mb()
    t_carga = time.perf_counter()
    it, motor = interprete(ruta)
    carga_ms = (time.perf_counter() - t_carga) * 1000
    ent = it.get_input_details()[0]
    x = np.random.default_rng(0).integers(0, 256, ent["shape"]).astype(ent["dtype"])   # foto de prueba fija
    media = m2 = 0.0
    minimo, maximo, n = math.inf, 0.0, 0
    for i in range(a.n + 5):
        it.set_tensor(ent["index"], x)
        t0 = time.perf_counter()
        it.invoke()
        ms = (time.perf_counter() - t0) * 1000
        if i < 5:
            continue                                   # calentamiento
        n += 1
        d = ms - media
        media += d / n
        m2 += d * (ms - media)
        minimo, maximo = min(minimo, ms), max(maximo, ms)
    desv = math.sqrt(m2 / (n - 1)) if n > 1 else 0.0
    rss1, pico = memoria_rss_mb()
    act = activaciones_minimas(it)
    tam = ruta.stat().st_size
    r = {"fecha": datetime.now().astimezone().isoformat(timespec="seconds"), "equipo": a.equipo,
         "sistema": f"{platform.system()} {platform.release()}", "cpu": platform.processor() or platform.machine(),
         "motor": motor, "hilos": os.cpu_count(), "modelo": info.get("version", ruta.name),
         "variante": info.get("variante"), "sintetico": info.get("sintetico"), "n": n,
         "media_ms": round(media, 3), "desv_ms": round(desv, 3), "min_ms": round(minimo, 3), "max_ms": round(maximo, 3),
         "carga_ms": round(carga_ms, 1), "rss_antes_mb": round(rss0, 1), "rss_despues_mb": round(rss1, 1),
         "rss_pico_mb": None if pico is None else round(pico, 1), "modelo_kb": round(tam / 1024),
         "activaciones_min_kb": round(act / 1024),
         "cabe_en_esp32": act <= ESP32_SRAM_LIBRE_B and tam <= ESP32_FLASH_APP_LIBRE_B}
    if a.corriente_ma:
        r["potencia_w"] = round(a.voltaje * a.corriente_ma / 1000, 3)
        r["energia_mj_por_inferencia"] = round(r["potencia_w"] * media, 3)       # W × ms = mJ
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(r, indent=2, ensure_ascii=False))
    print(f"\n{a.equipo}: {media:.2f} ± {desv:.2f} ms (n = {n}) · modelo {tam / 1024:.0f} KB · activaciones ≥ "
          f"{act / 1024:.0f} KB → {'cabe' if r['cabe_en_esp32'] else 'NO cabe'} en el ESP32 "
          f"(~{ESP32_SRAM_LIBRE_B // 1000} KB de SRAM libre, {ESP32_FLASH_APP_LIBRE_B // 1024} KB de flash libre)"
          + (" · modelo SINTÉTICO" if info.get("sintetico") else ""))


if __name__ == "__main__":
    main()
