"""R7 — informe de recursos: latencia por etapa (≥ 100 corridas, media ± desviación con Welford), CPU, RAM y
temperatura, en el equipo donde corra (se rotula: PC o Raspberry Pi). Sin ESP32 (salió del proyecto el 9-nov).

    viaviva r7 medir [--sesion <export.zip>] [--n 200] [--modelo <modelo_int8.tflite>]
    viaviva r7 consumo --estado reposo|grabando --ma 540 --v 5.08     (lectura del tester USB, a mano)
    viaviva r7 tabla                                                   (docs/R7.md y docs/img/r7_latencias.png)

Comparaciones previstas (si el docente pide otra plataforma): el MISMO código en PC vs. Pi, y umbrales vs. TFLite.
Cada corrida queda en data/logs/r7.jsonl (fuera de Git). Nada se escribe a mano salvo el consumo del tester.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from viaviva import config
from viaviva.nucleo import Detector, Nucleo, Welford

LOG = config.RAIZ / "data" / "logs" / "r7.jsonl"
LOG_CONSUMO = config.RAIZ / "data" / "logs" / "consumo.jsonl"
DOC = config.RAIZ / "docs" / "R7.md"
FIG = config.RAIZ / "docs" / "img" / "r7_latencias.png"


def equipo() -> str:
    try:
        modelo = Path("/proc/device-tree/model").read_text().strip("\x00 \n")
    except OSError:
        modelo = ""
    return modelo or f"PC {platform.node()} ({platform.processor() or platform.machine()})"


def rss_mb() -> float | None:
    if platform.system() == "Windows":
        class PMC(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong), ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t), ("a", ctypes.c_size_t), ("b", ctypes.c_size_t),
                        ("c", ctypes.c_size_t), ("d", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t)]
        c = PMC()
        c.cb = ctypes.sizeof(PMC)
        k32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
        k32.GetCurrentProcess.restype = ctypes.c_void_p            # el manejador es de 64 bits
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC), ctypes.c_ulong]
        if psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
            return round(c.WorkingSetSize / 2**20, 1)
        return None
    try:
        for linea in Path("/proc/self/status").read_text().splitlines():
            if linea.startswith("VmRSS:"):
                return round(int(linea.split()[1]) / 1024, 1)
    except OSError:
        pass
    return None


def temperatura() -> float | None:
    try:
        return round(int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000, 1)
    except (OSError, ValueError):
        return None


def _medir(f, n: int, calentamiento: int = 5) -> dict:
    for _ in range(calentamiento):
        f()
    w = Welford()
    for _ in range(n):
        t0 = time.perf_counter()
        f()
        w.agregar((time.perf_counter() - t0) * 1e3)
    return w.resumen(4)


def _senal_prueba(ruta: Path | None):
    from viaviva.senal import cargar, preparar
    if ruta:
        return cargar(ruta)
    rnd = np.random.default_rng(0)                  # 60 s a 100 Hz con ruido de vía (sin sesión real)
    t = np.arange(0, 60, 0.01)
    z = 9.81 + rnd.normal(0, 0.3, len(t))
    gps = [[s, 5.535, -73.37 + s * 4.5e-5, 2800, 5.0] for s in range(60)]
    return preparar(t, rnd.normal(0, 0.2, len(t)), rnd.normal(0, 0.2, len(t)), z, gps)


def medir(n: int = 200, sesion: Path | None = None, modelo: Path | None = None) -> dict:
    from viaviva import detector, ventanas
    s = _senal_prueba(sesion)
    p = detector.cargar_parametros(detector.RUTA_CONFIG)
    det = Detector(100.0)
    bloque = [float(x) for x in s.a_v[:100]]
    etapas: dict[str, dict] = {}
    cpu0, pared0 = time.process_time(), time.perf_counter()

    etapas["detector_en_vivo_1s_100_muestras_ms"] = _medir(lambda: [det.muestra(a, 20.0) for a in bloque], n)
    nucleo = Nucleo(100.0, dir_grabaciones=Path(os.devnull).parent)
    lote = [(i / 100, 0.1, 0.2, 9.81) for i in range(25)]
    k = [0]

    def lote_nucleo():
        k[0] += 1
        nucleo.acc([(k[0] * 0.25 + t, x, y, z) for t, x, y, z in lote])
    etapas["nucleo_lote_25_muestras_ms"] = _medir(lote_nucleo, n)
    seg = max(0, min(len(s.t) - 3000, 1000))
    corte = type(s)(s.nombre, s.fs, s.t[seg:seg + 3000], s.a_v[seg:seg + 3000], s.a_h[seg:seg + 3000],
                    s.vel_kmh[seg:seg + 3000], s.lat[seg:seg + 3000], s.lon[seg:seg + 3000], s.hueco_datos[seg:seg + 3000])
    def detector_completo():                       # sin la caché de características: la etapa entera
        corte.__dict__.pop("_cache_caracteristicas", None)
        detector.detectar(corte, p)
    etapas["detector_v2_30s_ms"] = _medir(detector_completo, max(100, n // 4))
    v, h, vel = s.a_v[1000:1200], s.a_h[1000:1200], s.vel_kmh[1000:1200]
    etapas["caracteristicas_ventana_2s_ms"] = _medir(lambda: ventanas.caracteristicas_ventana(v, h, vel, s.fs), n)
    if modelo:
        etapas.update(_medir_tflite(Path(modelo), n))
    cpu = 100 * (time.process_time() - cpu0) / max(1e-9, time.perf_counter() - pared0) / (os.cpu_count() or 1)
    fila = {"ts_utc": datetime.now(UTC).isoformat(timespec="seconds"), "equipo": equipo(), "sistema": platform.platform(),
            "python": platform.python_version(), "nucleos": os.cpu_count(), "n": n,
            "sesion": sesion.name if sesion else "señal de prueba 60 s (sin sesión real)", "etapas": etapas,
            "modelo": (f"{modelo.parent.name}/{modelo.name}" if modelo else None),
            "cpu_pct_proceso": round(cpu, 1), "rss_mb": rss_mb(), "temp_c": temperatura()}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    return fila


def _medir_tflite(ruta: Path, n: int) -> dict:
    try:
        from ai_edge_litert.interpreter import Interpreter
    except ImportError:
        try:
            import tensorflow as tf
            Interpreter = tf.lite.Interpreter
        except (ImportError, AttributeError):
            return {"tflite_ventana_ms": {"error": "sin ai-edge-litert ni TensorFlow en este entorno"}}
    it = Interpreter(model_path=str(ruta))
    it.allocate_tensors()
    ent = it.get_input_details()[0]
    x = np.zeros(ent["shape"], dtype=ent["dtype"])

    def inferir():
        it.set_tensor(ent["index"], x)
        it.invoke()
    return {"tflite_ventana_ms": _medir(inferir, n)}


def consumo(estado: str, ma: float, v: float) -> dict:
    fila = {"ts_utc": datetime.now(UTC).isoformat(timespec="seconds"), "equipo": equipo(), "estado": estado,
            "ma": ma, "v": v, "w": round(ma * v / 1000, 3)}
    LOG_CONSUMO.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_CONSUMO, "a", encoding="utf-8") as f:
        f.write(json.dumps(fila) + "\n")
    return fila


def _lineas(ruta: Path) -> list[dict]:
    if not ruta.exists():
        return []
    return [json.loads(x) for x in ruta.read_text(encoding="utf-8").splitlines() if x.strip()]


def tabla() -> str:
    filas = _lineas(LOG)
    ultimos = {}
    for f in filas:                               # la última medición de cada equipo
        ultimos[f["equipo"]] = f
    etapas = sorted({e for f in ultimos.values() for e in f["etapas"]})
    eq = list(ultimos)
    l = ["# R7 — informe de recursos", "", f"Generado {datetime.now():%Y-%m-%d %H:%M} con `viaviva r7 tabla` a partir de "
         "`data/logs/r7.jsonl`. Media ± desviación estándar (Welford) en milisegundos; n = corridas por etapa "
         "(5 de calentamiento no cuentan).", ""]
    if not eq:
        return "\n".join(l + ["[PENDIENTE: correr `viaviva r7 medir` en el PC y en la Pi]", ""])
    rotulo = [q if "Raspberry" in q else f"{q} — **provisional, PC**" for q in eq]   # R7 se mide en la Pi
    l += ["| Etapa | " + " | ".join(rotulo) + " |", "|---|" + "---|" * len(eq)]
    for e in etapas:
        celdas = []
        for q in eq:
            d = ultimos[q]["etapas"].get(e)
            celdas.append("—" if not d else d.get("error", f"{d['media']:.4g} ± {d['desv']:.2g} (n = {d['n']})"))
        l.append(f"| {e} | " + " | ".join(celdas) + " |")
    l += ["| CPU del proceso durante la medición (%) | " + " | ".join(str(ultimos[q]["cpu_pct_proceso"]) for q in eq) + " |",
          "| RAM del proceso (MB) | " + " | ".join(str(ultimos[q]["rss_mb"] or "—") for q in eq) + " |",
          "| Temperatura del SoC (°C) | " + " | ".join(str(ultimos[q]["temp_c"] or "—") for q in eq) + " |"]
    cons = _lineas(LOG_CONSUMO)
    l += ["", "## Consumo (tester USB, anotado a mano)", ""]
    l += [f"- {c['equipo']} · {c['estado']}: {c['ma']} mA × {c['v']} V = {c['w']} W ({c['ts_utc']})" for c in cons] \
        or ["- [PENDIENTE: medir en la Pi con el Charger Doctor, en reposo y grabando]"]
    if not any("Raspberry" in q for q in eq):
        l += ["", "**Raspberry Pi:** [PENDIENTE: correr `viaviva r7 medir` en la Pi]."]
    l += ["", "Señal: " + "; ".join(f"{q}: {ultimos[q]['sesion']}" for q in eq) + ".",
          "Comparaciones previstas: el mismo código en PC vs. Pi; umbrales vs. TFLite (`--modelo`).",
          "TFLite: el modelo de ventanas actual es SINTÉTICO (esqueleto, sin datos etiquetados); su latencia no depende de "
          "los datos de entrenamiento, su exactitud sí (no se reporta)."]
    return "\n".join(l) + "\n"


def figura() -> Path | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    ultimos = {}
    for f in _lineas(LOG):
        ultimos[f["equipo"]] = f
    if not ultimos:
        return None
    etapas = sorted({e for f in ultimos.values() for e, d in f["etapas"].items() if "media" in d})
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ancho = 0.8 / len(ultimos)
    for i, (q, f) in enumerate(ultimos.items()):
        med = [f["etapas"].get(e, {}).get("media", 0) for e in etapas]
        des = [f["etapas"].get(e, {}).get("desv", 0) for e in etapas]
        ax.bar(np.arange(len(etapas)) + i * ancho, med, ancho, yerr=des, capsize=3, label=q[:40])
    ax.set_xticks(np.arange(len(etapas)) + ancho * (len(ultimos) - 1) / 2,
                  [e.replace("_ms", "").replace("_", " ") for e in etapas], rotation=15, ha="right", fontsize=8)
    ax.set_ylabel("ms (media ± desv.)")
    ax.set_yscale("log")
    ax.legend(fontsize=7)
    fig.tight_layout()
    FIG.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG, dpi=150)
    return FIG


def main():
    ap = argparse.ArgumentParser(prog="viaviva r7", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("medir")
    m.add_argument("--n", type=int, default=200)
    m.add_argument("--sesion", type=Path)
    m.add_argument("--modelo", type=Path)
    c = sub.add_parser("consumo")
    c.add_argument("--estado", choices=["reposo", "grabando"], required=True)
    c.add_argument("--ma", type=float, required=True)
    c.add_argument("--v", type=float, required=True)
    sub.add_parser("tabla")
    a = ap.parse_args()
    if a.cmd == "medir":
        print(json.dumps(medir(max(100, a.n), a.sesion, a.modelo), ensure_ascii=False, indent=1))
    elif a.cmd == "consumo":
        print(consumo(a.estado, a.ma, a.v))
    else:
        DOC.write_text(tabla(), encoding="utf-8")
        f = figura()
        print(DOC.read_text(encoding="utf-8"))
        print(f"→ {DOC}" + (f" · {f}" if f else " (sin matplotlib: sin figura)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
