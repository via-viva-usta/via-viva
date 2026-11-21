"""Compara el detector EN VIVO (`viaviva/nucleo.py`, |a| − 1 g, pico a pico en 50 ms) con el detector de ANÁLISIS
(`viaviva/detector.py` + `config/detector.yaml`, eje vertical normalizado por velocidad) sobre las MISMAS sesiones y
las MISMAS marcas, con la misma tolerancia y las mismas clases positivas. No cambia ningún umbral.

    python -m herramientas.comparar_detectores <sesión o export…> [--sensor adxl2|mpu6050] [--html f.html] [--json f.json]

Por sesión: eventos de cada detector, TP/FP/FN contra las marcas, cuántos eventos coinciden entre los dos (± tolerancia),
y si la repetición del detector en vivo reproduce `eventos.csv` (prueba de que la comparación es fiel). El HTML (sin
internet ni coordenadas) dibuja la señal de cada detector, la velocidad, las marcas y los eventos para revisar a ojo
los desacuerdos. Solo lectura: no escribe en la carpeta de la sesión.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sys
from pathlib import Path

import numpy as np

from viaviva import detector
from viaviva.fuentes import _leer_tabla
from viaviva.nucleo import G, Detector
from viaviva.senal import cargar, leer_etiquetas, preparar, sesiones_en

ARCHIVO_SENSOR = {"principal": "Accelerometer.csv", "adxl2": "Accelerometer_adxl2.csv",
                  "mpu6050": "Accelerometer_mpu6050.csv"}


def repetir_en_vivo(acc: list[list[float]], gps: list[list[float]], fs: float) -> list[dict]:
    """El detector en vivo muestra a muestra, con la velocidad del último punto GPS (como en la captura)."""
    det = Detector(fs)
    tg = [f[0] for f in gps if len(f) > 4 and not math.isnan(f[4])]
    vg = [f[4] * 3.6 for f in gps if len(f) > 4 and not math.isnan(f[4])]
    k, vel, eventos = 0, 0.0, []
    for t, x, y, z in (f[:4] for f in acc):
        while k < len(tg) and tg[k] <= t:
            vel, k = vg[k], k + 1
        p2p = det.muestra(math.sqrt(x * x + y * y + z * z) / G - 1.0, vel)
        if p2p is not None:
            eventos.append({"t_s": round(t, 3), "p2p_g": round(p2p, 3), "vel_kmh": round(vel, 1)})
    return eventos


def coinciden(a: list[dict], b: list[dict], tol: float) -> int:
    tb = sorted(e["t_s"] for e in b)
    usados, n = set(), 0
    for e in a:
        cand = [(abs(t - e["t_s"]), i) for i, t in enumerate(tb) if i not in usados and abs(t - e["t_s"]) <= tol]
        if cand:
            usados.add(min(cand)[1])
            n += 1
    return n


def comparar(ruta: Path, sensor: str = "principal") -> dict:
    p = detector.cargar_parametros()
    nombre_csv = ARCHIVO_SENSOR[sensor]
    acc = [f for f in _leer_tabla(ruta, nombre_csv) if len(f) >= 4 and not math.isnan(f[0])]
    if len(acc) < 200:
        return {"sesion": ruta.name, "sensor": sensor, "error": f"{nombre_csv}: sin datos suficientes ({len(acc)})"}
    gps = _leer_tabla(ruta, "Location.csv")
    if sensor == "principal":
        s = cargar(ruta)
    else:
        s = preparar([f[0] for f in acc], [f[1] for f in acc], [f[2] for f in acc], [f[3] for f in acc], gps,
                     nombre=ruta.name)
        s.etiquetas = [(t - acc[0][0], c) for t, c in leer_etiquetas(ruta)]
    t0 = acc[0][0]
    fs = (len(acc) - 1) / (acc[-1][0] - t0)
    vivo = [{**e, "t_s": round(e["t_s"] - t0, 3)} for e in repetir_en_vivo(acc, gps, fs)]
    analisis = detector.detectar(s, p)
    tol = p["tolerancia_s"]
    r = {"sesion": ruta.name, "sensor": sensor, "fs_hz": round(fs, 1), "dur_s": round(float(s.t[-1]), 1),
         "marcas": len(s.etiquetas), "tolerancia_s": tol, "version_analisis": p.get("version"),
         "en_vivo": {"eventos": len(vivo), **detector.metricas(**{k: v for k, v in detector.emparejar(
             vivo, s.etiquetas, p).items() if k in ("tp", "fp", "fn")})},
         "analisis": {"eventos": len(analisis), **detector.metricas(**{k: v for k, v in detector.emparejar(
             analisis, s.etiquetas, p).items() if k in ("tp", "fp", "fn")})},
         "coinciden_entre_si": coinciden(vivo, analisis, tol)}
    for nombre, ev in (("en_vivo", vivo), ("analisis", analisis)):
        por = detector.emparejar(ev, s.etiquetas, p)["por_clase"]
        r[nombre]["por_clase"] = {c: f"{d['detectadas']}/{d['marcas']}" for c, d in sorted(por.items())}
    grabados = []
    if sensor == "principal" and ruta.is_dir() and (ruta / "eventos.csv").exists():
        grabados = [{"t_s": f[0] - t0} for f in _leer_tabla(ruta, "eventos.csv") if f and not math.isnan(f[0])]
        r["repeticion_fiel"] = {"eventos_csv": len(grabados), "repetidos_a_0_1s": coinciden(grabados, vivo, 0.1)}
    r["_trazos"] = {"senal": s, "vivo": vivo, "analisis": analisis, "grabados": grabados, "acc": acc, "t0": t0}
    return r


# ------------------------------------------------------------------------------------------------ HTML
COLORES = {"hueco": "#d62728", "resalto": "#ff7f0e", "tapa": "#9467bd", "grieta": "#8c564b", "parche": "#7f7f7f",
           "via_buena": "#2ca02c", "obstaculo": "#e377c2"}


def _envolvente(t: np.ndarray, y: np.ndarray, paso: float) -> tuple[np.ndarray, np.ndarray]:
    """Máximo y mínimo por intervalo de `paso` s (dibujo liviano sin perder los picos)."""
    k = np.floor((t - t[0]) / paso).astype(int)
    n = k[-1] + 1
    mx, mn = np.full(n, -np.inf), np.full(n, np.inf)
    np.maximum.at(mx, k, y)
    np.minimum.at(mn, k, y)
    return mx, mn


def svg_sesion(r: dict, px_s: float = 4.0, paso: float = 0.1) -> str:
    tr = r["_trazos"]
    s, acc, t0 = tr["senal"], tr["acc"], tr["t0"]
    dur = float(s.t[-1])
    ancho, alto_pista = int(dur * px_s) + 60, 120
    t_vivo = np.array([f[0] - t0 for f in acc])
    a_vivo = np.array([math.sqrt(f[1] ** 2 + f[2] ** 2 + f[3] ** 2) / G - 1.0 for f in acc])
    pistas = [("|a| − 1 g (en vivo)", t_vivo, a_vivo), ("a vertical (análisis)", s.t, s.a_v)]
    partes = []
    y0 = 20
    for titulo, t, y in pistas:
        mx, mn = _envolvente(t, y, paso)
        esc = (alto_pista / 2 - 4) / max(0.5, float(np.nanmax(np.abs(np.r_[mx, mn]))))
        xs = 50 + np.arange(len(mx)) * paso * px_s
        medio = y0 + alto_pista / 2
        puntos = " ".join(f"{x:.1f},{medio - a * esc:.1f} {x:.1f},{medio - b * esc:.1f}" for x, a, b in zip(xs, mx, mn))
        partes.append(f'<text x="4" y="{y0 + 12}" class="t">{html.escape(titulo)}</text>'
                      f'<polyline points="{puntos}" class="s"/>'
                      f'<line x1="50" x2="{ancho}" y1="{medio}" y2="{medio}" class="cero"/>')
        y0 += alto_pista + 10
    vel = np.nan_to_num(s.vel_kmh)
    mx, _ = _envolvente(s.t, vel, 1.0)
    xs = 50 + np.arange(len(mx)) * px_s
    partes.append(f'<text x="4" y="{y0 + 12}" class="t">velocidad (0–40 km/h)</text><polyline class="v" points="'
                  + " ".join(f"{x:.1f},{y0 + 60 - min(v, 40) * 1.5:.1f}" for x, v in zip(xs, mx)) + '"/>')
    alto = y0 + 70
    for t, c in s.etiquetas:
        x = 50 + t * px_s
        partes.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="10" y2="{alto}" stroke="{COLORES.get(c, "#000")}" '
                      f'class="m"><title>{html.escape(c)} t={t:.1f} s</title></line>')
    for clave, y, forma in (("grabados", 22, "▼"), ("vivo", 34, "▲"), ("analisis", 20 + alto_pista + 22, "●")):
        for e in tr[clave]:
            partes.append(f'<text x="{50 + e["t_s"] * px_s - 4:.1f}" y="{y}" class="e {clave}">{forma}'
                          f'<title>{clave} t={e["t_s"]:.2f} s</title></text>')
    for k in range(0, int(dur) + 1, 30):
        partes.append(f'<text x="{50 + k * px_s:.1f}" y="{alto + 12}" class="t">{k // 60}:{k % 60:02d}</text>')
    return f'<svg width="{ancho}" height="{alto + 20}" xmlns="http://www.w3.org/2000/svg">{"".join(partes)}</svg>'


def html_informe(resultados: list[dict]) -> str:
    leyenda = " ".join(f'<span style="color:{v}">┃ {k}</span>' for k, v in COLORES.items())
    cuerpo = []
    for r in resultados:
        if "error" in r:
            cuerpo.append(f"<h2>{html.escape(r['sesion'])}</h2><p>{html.escape(r['error'])}</p>")
            continue
        tabla = "".join(f"<tr><td>{n}</td><td>{d['eventos']}</td><td>{d['tp']}</td><td>{d['fp']}</td><td>{d['fn']}"
                        f"</td><td>{d['precision']}</td><td>{d['exhaustividad']}</td><td>{d['f1']}</td></tr>"
                        for n, d in (("en vivo", r["en_vivo"]), ("análisis", r["analisis"])))
        cuerpo.append(f"<h2>{html.escape(r['sesion'])} · sensor {r['sensor']} · {r['fs_hz']} Hz · {r['dur_s']} s</h2>"
                      f"<table><tr><th>detector</th><th>eventos</th><th>TP</th><th>FP</th><th>FN</th><th>P</th>"
                      f"<th>R</th><th>F1</th></tr>{tabla}</table><p>Coinciden entre sí: {r['coinciden_entre_si']} "
                      f"(± {r['tolerancia_s']} s). Marcas: {r['marcas']}.</p><div class='scroll'>{svg_sesion(r)}</div>")
    return ("<!doctype html><meta charset='utf-8'><title>Comparación de detectores</title><style>"
            "body{font:14px system-ui;margin:16px}table{border-collapse:collapse}td,th{border:1px solid #ccc;"
            "padding:2px 8px}.scroll{overflow-x:auto;border:1px solid #ddd}.s{fill:none;stroke:#1f77b4;"
            "stroke-width:.6}.v{fill:none;stroke:#555}.cero{stroke:#bbb}.m{stroke-width:1;opacity:.7}.t{font-size:11px}"
            ".e{font-size:10px}.vivo{fill:#1f77b4}.analisis{fill:#d62728}.grabados{fill:#999}</style>"
            "<h1>Detector en vivo frente a detector de análisis</h1><p>▼ eventos.csv grabado · ▲ en vivo repetido · "
            f"● análisis · líneas = marcas: {leyenda}</p><p>Las cifras valen solo para estas sesiones y estas marcas; "
            "no fijan umbrales.</p>" + "".join(cuerpo))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("rutas", nargs="+", type=Path)
    ap.add_argument("--sensor", choices=list(ARCHIVO_SENSOR), default="principal")
    ap.add_argument("--html", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    resultados = [comparar(r, a.sensor) for r in sesiones_en(a.rutas)]
    limpio = [{k: v for k, v in r.items() if k != "_trazos"} for r in resultados]
    print(json.dumps(limpio, ensure_ascii=False, indent=1))
    if a.json:
        a.json.write_text(json.dumps(limpio, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.html:
        a.html.write_text(html_informe(resultados), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
