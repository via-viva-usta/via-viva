"""Constructor del dataset de ventanas (Fase B) y evaluación de un clasificador sencillo por salida completa.

    viaviva dataset construir <sesiones…> [--fotos data/procesado/metadatos.csv]
    viaviva dataset evaluar <manifest.csv>

- Ventanas de 2 s con 50 % de solape a 100 Hz (200 muestras, paso 1 s).
- Características: RMS, pico, pico a pico, curtosis, factor de cresta y jerk máximo del eje vertical; energía en bandas
  0–2, 2–5, 5–10, 10–20 y 20–50 Hz (FFT con ventana de Hann); RMS horizontal; velocidad media del GPS.
- Etiqueta = la marca más cercana al centro de la ventana a ± 1,5 s; si no hay, `sin_marca` (no se usa para entrenar
  ni se toma como "vía buena"). Ventanas con el carro detenido (< 2 km/h) = `quieto`; con datos interpolados > 10 % =
  `hueco_datos` (se excluyen).
- Fotos de campo: cada foto (metadatos del dataset de fotos) se asocia a la ventana más cercana a ≤ 30 m y ± 10 min.
Salida en `data/procesado/dataset_ventanas/<fecha>/`: manifest.csv, calidad.md y fotos_asociadas.csv (fuera de Git).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from viaviva import config
from viaviva.estructuras import distancia_m
from viaviva.senal import Senal, cargar, sesiones_en

SALIDAS = config.RAIZ / "data" / "procesado" / "dataset_ventanas"
VENTANA_S, PASO_S, TOLERANCIA_S = 2.0, 1.0, 1.5
BANDAS = [(0, 2), (2, 5), (5, 10), (10, 20), (20, 50)]
CARACTERISTICAS = ["rms_v", "pico_v", "p2p_v", "curtosis_v", "cresta_v", "jerk_max", *[f"e_{a}_{b}hz" for a, b in BANDAS],
                   "rms_h", "vel_kmh"]


def caracteristicas_ventana(v: np.ndarray, h: np.ndarray, vel: np.ndarray, fs: float) -> dict:
    v = v - v.mean()
    rms = float(np.sqrt(np.mean(v ** 2)))
    pico = float(np.max(np.abs(v)))
    sd = float(np.std(v))
    curt = float(np.mean((v / sd) ** 4)) if sd > 0 else 0.0
    espectro = np.abs(np.fft.rfft(v * np.hanning(len(v)))) ** 2
    frec = np.fft.rfftfreq(len(v), 1.0 / fs)
    total = float(espectro.sum()) or 1.0
    d = {"rms_v": rms, "pico_v": pico, "p2p_v": float(v.max() - v.min()), "curtosis_v": curt,
         "cresta_v": pico / rms if rms > 0 else 0.0, "jerk_max": float(np.max(np.abs(np.diff(v))) * fs),
         "rms_h": float(np.sqrt(np.mean(h ** 2))), "vel_kmh": float(np.nanmean(vel)) if np.any(~np.isnan(vel)) else math.nan}
    for a, b in BANDAS:
        d[f"e_{a}_{b}hz"] = float(espectro[(frec >= a) & (frec < b)].sum() / total)
    return {k: round(x, 5) if isinstance(x, float) and not math.isnan(x) else x for k, x in d.items()}


def ventanas(s: Senal) -> list[dict]:
    n, paso = int(VENTANA_S * s.fs), int(PASO_S * s.fs)
    marcas = s.etiquetas
    filas = []
    for k, i in enumerate(range(0, len(s.t) - n + 1, paso)):
        sl = slice(i, i + n)
        t0, t1 = float(s.t[i]), float(s.t[i + n - 1])
        centro = (t0 + t1) / 2
        cerca = [(abs(t - centro), c) for t, c in marcas if abs(t - centro) <= TOLERANCIA_S]
        etiqueta = min(cerca)[1] if cerca else "sin_marca"
        vel = s.vel_kmh[sl]
        estado = "ok"
        if float(np.mean(s.hueco_datos[sl])) > 0.1:
            estado = "hueco_datos"
        elif np.any(~np.isnan(vel)) and float(np.nanmean(vel)) < 2.0:
            estado = "quieto"
        medio = i + n // 2
        filas.append({"sesion": s.nombre, "ventana": k, "t0_s": round(t0, 2), "t1_s": round(t1, 2),
                      "utc_centro": (datetime.fromtimestamp(s.inicio_epoch + centro, timezone.utc).isoformat(
                          timespec="seconds") if s.inicio_epoch else ""),
                      "lat": None if math.isnan(s.lat[medio]) else round(float(s.lat[medio]), 7),
                      "lon": None if math.isnan(s.lon[medio]) else round(float(s.lon[medio]), 7),
                      "etiqueta": etiqueta, "estado": estado,
                      **caracteristicas_ventana(s.a_v[sl], s.a_h[sl], vel, s.fs)})
    return filas


def asociar_fotos(filas: list[dict], ruta_fotos: Path) -> list[dict]:
    """Foto ↔ ventana más cercana a ≤ 30 m y ± 10 min (hora local UTC-5 de los metadatos de fotos)."""
    if not ruta_fotos or not Path(ruta_fotos).exists():
        return []
    with open(ruta_fotos, encoding="utf-8-sig") as f:
        fotos = list(csv.DictReader(f))
    con_pos = [w for w in filas if w["lat"] is not None and w["utc_centro"]]
    salida = []
    for foto in fotos:
        try:
            lat, lon = float(foto["lat"]), float(foto["lon"])
            local = datetime.fromisoformat(f"{foto['fecha']}T{foto['hora']}").replace(tzinfo=timezone(timedelta(hours=-5)))
        except (KeyError, ValueError):
            continue
        mejor = None
        for w in con_pos:
            dt = abs((datetime.fromisoformat(w["utc_centro"]) - local).total_seconds())
            if dt > 600:
                continue
            d = distancia_m(lat, lon, w["lat"], w["lon"])
            if d <= 30 and (mejor is None or d < mejor[0]):
                mejor = (d, dt, w)
        if mejor:
            salida.append({"foto_id": foto.get("id"), "archivo": foto.get("archivo"), "clase_foto": foto.get("clase"),
                           "sesion": mejor[2]["sesion"], "ventana": mejor[2]["ventana"],
                           "etiqueta_ventana": mejor[2]["etiqueta"], "distancia_m": round(mejor[0], 1),
                           "desfase_s": round(mejor[1])})
    return salida


def calidad(filas: list[dict], n_fotos: int, n_fotos_asociadas: int) -> str:
    validas = [w for w in filas if w["estado"] == "ok"]
    marcadas = [w for w in validas if w["etiqueta"] != "sin_marca"]
    cuenta = Counter(w["etiqueta"] for w in marcadas)
    l = [f"# Calidad del dataset de ventanas", "", f"Generado {datetime.now():%Y-%m-%d %H:%M}. Ventanas de {VENTANA_S:.0f} s "
         f"con 50 % de solape; etiqueta a ± {TOLERANCIA_S} s del centro.", "",
         "| Sesión | Ventanas | Válidas | Quieto | Con huecos de datos | Con marca | Sin GPS |", "|---|---|---|---|---|---|---|"]
    for s in sorted({w["sesion"] for w in filas}):
        ws = [w for w in filas if w["sesion"] == s]
        l.append(f"| {s} | {len(ws)} | {sum(w['estado'] == 'ok' for w in ws)} | {sum(w['estado'] == 'quieto' for w in ws)} "
                 f"| {sum(w['estado'] == 'hueco_datos' for w in ws)} | "
                 f"{sum(w['estado'] == 'ok' and w['etiqueta'] != 'sin_marca' for w in ws)} | "
                 f"{sum(w['lat'] is None for w in ws)} |")
    l += ["", "## Clases (ventanas válidas con marca)", ""]
    l += [f"- {c}: {n}" for c, n in cuenta.most_common()] or ["- **Ninguna ventana tiene marca todavía**: hay que "
                                                              "etiquetar las salidas (captura en vivo o contra el video)."]
    if cuenta:
        mayor, menor = max(cuenta.values()), min(cuenta.values())
        l += ["", f"Desbalance mayor/menor = {mayor / menor:.1f}." + (" **Desbalanceado** (> 5): usar pesos por clase."
                                                                      if mayor / menor > 5 else "")]
        pocas = [c for c, n in cuenta.items() if n < 20]
        if pocas:
            l.append(f"Clases con < 20 ventanas (no concluyentes): {', '.join(pocas)}.")
    l += ["", f"Fotos de campo: {n_fotos_asociadas} de {n_fotos} asociadas a una ventana (≤ 30 m, ± 10 min)."]
    return "\n".join(l) + "\n"


def construir(rutas: list[Path], fotos: Path | None = None, salida: Path | None = None) -> Path:
    filas = []
    for r in sesiones_en(rutas):
        filas += ventanas(cargar(r))
    salida = Path(salida) if salida else SALIDAS / datetime.now().strftime("%Y-%m-%d_%H%M")
    salida.mkdir(parents=True, exist_ok=True)
    with open(salida / "manifest.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    asociadas = asociar_fotos(filas, fotos) if fotos else []
    if asociadas:
        with open(salida / "fotos_asociadas.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(asociadas[0]))
            w.writeheader()
            w.writerows(asociadas)
    n_fotos = sum(1 for _ in open(fotos, encoding="utf-8-sig")) - 1 if fotos and Path(fotos).exists() else 0
    (salida / "calidad.md").write_text(calidad(filas, n_fotos, len(asociadas)), encoding="utf-8")
    return salida


def evaluar(manifest: Path) -> dict:
    """Bosque aleatorio sobre las características, validación dejando una SALIDA completa afuera (sin fugas).
    Solo ventanas válidas con marca. Devuelve P, R y F1 por clase y la matriz de confusión."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
    with open(manifest, encoding="utf-8") as f:
        filas = [w for w in csv.DictReader(f) if w["estado"] == "ok" and w["etiqueta"] != "sin_marca"]
    sesiones = sorted({w["sesion"] for w in filas})
    clases = sorted({w["etiqueta"] for w in filas})
    if len(sesiones) < 2 or len(clases) < 2:
        return {"error": f"Hacen falta ≥ 2 salidas y ≥ 2 clases con marcas (hay {len(sesiones)} salidas y "
                         f"{len(clases)} clases)."}
    X = np.array([[float(w[c]) if w[c] not in ("", "nan") else 0.0 for c in CARACTERISTICAS] for w in filas])
    y = np.array([w["etiqueta"] for w in filas])
    g = np.array([w["sesion"] for w in filas])
    pred = np.empty_like(y)
    for s in sesiones:
        m = g == s
        modelo = RandomForestClassifier(n_estimators=200, class_weight="balanced", random_state=0)
        modelo.fit(X[~m], y[~m])
        pred[m] = modelo.predict(X[m])
    p, r, f1, n = precision_recall_fscore_support(y, pred, labels=clases, zero_division=0)
    return {"salidas": sesiones, "clases": clases, "n": len(y),
            "por_clase": {c: {"precision": round(float(p[i]), 3), "exhaustividad": round(float(r[i]), 3),
                              "f1": round(float(f1[i]), 3), "soporte": int(n[i])} for i, c in enumerate(clases)},
            "matriz_confusion": confusion_matrix(y, pred, labels=clases).tolist()}


def main():
    ap = argparse.ArgumentParser(prog="viaviva dataset", description="Dataset de ventanas")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("construir")
    c.add_argument("sesiones", nargs="+")
    c.add_argument("--fotos", default=str(config.RAIZ / "data" / "procesado" / "metadatos.csv"))
    c.add_argument("--salida")
    e = sub.add_parser("evaluar")
    e.add_argument("manifest")
    a = ap.parse_args()
    if a.cmd == "construir":
        ruta = construir(a.sesiones, Path(a.fotos), a.salida)
        print((ruta / "calidad.md").read_text(encoding="utf-8"))
        print(f"→ {ruta}")
    else:
        r = evaluar(Path(a.manifest))
        print(json.dumps(r, ensure_ascii=False, indent=1))
        (Path(a.manifest).parent / "evaluacion.json").write_text(json.dumps(r, ensure_ascii=False, indent=1),
                                                                 encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
