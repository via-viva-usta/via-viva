"""Detector por umbrales calibrable (Fase B): pico, RMS en ventana, jerk y normalización por velocidad del GPS.

    viaviva detector detectar <sesión>                 eventos de una sesión (CSV)
    viaviva detector evaluar <sesiones…>               P, R y F1 contra las marcas, sin calibrar
    viaviva detector calibrar <sesiones…>              búsqueda de umbrales con validación dejando UNA SALIDA afuera
Parámetros en `config/detector.yaml`. Salidas en `data/procesado/detector/<fecha>/` (fuera de Git).

Evento = (t, lat, lon, vel, amplitud normalizada, severidad baja/media/alta, confianza).
Confianza = 1 − 1/m, con m = el menor de los tres cocientes valor/umbral (m = 1 → 0; m = 2 → 0,5; m = 4 → 0,75):
dice cuánto margen tuvo el criterio más justo, no es una probabilidad calibrada.
"""
from __future__ import annotations

import argparse
import copy
import csv
import itertools
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

from viaviva import config
from viaviva.senal import Senal, cargar, sesiones_en

RUTA_CONFIG = config.RAIZ / "config" / "detector.yaml"
RUTA_CALIBRADO = config.RAIZ / "config" / "detector_calibrado.yaml"
SALIDAS = config.RAIZ / "data" / "procesado" / "detector"


def cargar_parametros(ruta: Path | None = None) -> dict:
    ruta = Path(ruta) if ruta else (RUTA_CALIBRADO if RUTA_CALIBRADO.exists() else RUTA_CONFIG)
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


def _max_movil(x: np.ndarray, n: int) -> np.ndarray:
    """Máximo en una ventana centrada de n muestras (O(N·n), n pequeño)."""
    m = len(x)
    medio = n // 2
    rel = np.pad(x, (medio, n - medio - 1), mode="edge")
    return np.max(np.lib.stride_tricks.sliding_window_view(rel, n), axis=1)[:m]


def caracteristicas(s: Senal, p: dict) -> dict[str, np.ndarray]:
    """Se calculan una vez por sesión y por ventanas/velocidad: la calibración solo cambia los umbrales."""
    llave = tuple(p[k] for k in ("ventana_pico_s", "ventana_rms_s", "tau_fondo_s", "v_min_kmh", "v_ref_kmh",
                                 "exponente_velocidad"))
    cache = s.__dict__.setdefault("_cache_caracteristicas", {})
    if llave not in cache:
        cache[llave] = _caracteristicas(s, p)
    return cache[llave]


def _caracteristicas(s: Senal, p: dict) -> dict[str, np.ndarray]:
    fs = s.fs
    n_pico = max(2, int(round(p["ventana_pico_s"] * fs)))
    n_rms = max(2, int(round(p["ventana_rms_s"] * fs)))
    pico = _max_movil(np.abs(s.a_v), n_pico)
    jerk = _max_movil(np.abs(np.gradient(s.a_v, 1.0 / fs)), n_pico)
    rms_local = np.sqrt(np.convolve(s.a_v ** 2, np.ones(n_rms) / n_rms, mode="same"))
    alfa = 1.0 / (p["tau_fondo_s"] * fs)
    fondo = np.empty_like(s.a_v)
    ms = float(np.mean(s.a_v[: int(fs)] ** 2))
    for i, v in enumerate(s.a_v):          # valor ANTERIOR (un golpe no se tapa a sí mismo)
        fondo[i] = ms
        ms += alfa * (v * v - ms)
    rms_fondo = np.sqrt(np.maximum(fondo, 1e-8))
    vel = np.nan_to_num(s.vel_kmh, nan=0.0)
    factor = (np.maximum(vel, p["v_min_kmh"]) / p["v_ref_kmh"]) ** p["exponente_velocidad"]
    return {"pico": pico, "jerk": jerk, "rms_local": rms_local, "rms_fondo": rms_fondo, "amp_norm": pico / factor,
            "vel": vel}


def detectar(s: Senal, p: dict) -> list[dict]:
    c = caracteristicas(s, p)
    r_pico = c["amp_norm"] / p["umbral_pico_g"]
    r_fondo = c["pico"] / (p["umbral_rel_fondo"] * c["rms_fondo"])
    r_jerk = c["jerk"] / p["umbral_jerk_g_s"]
    m = np.minimum(np.minimum(r_pico, r_fondo), r_jerk)
    candidato = (m > 1.0) & (c["vel"] > p["v_min_kmh"]) & ~s.hueco_datos
    candidato[: int(p["tau_fondo_s"] * s.fs)] = False          # calentamiento del fondo
    eventos, refr = [], int(p["refractario_s"] * s.fs)
    i, n = 0, len(candidato)
    while i < n:
        if not candidato[i]:
            i += 1
            continue
        j = min(n, i + refr)                                   # todo lo que cae en el refractario
        k = i + int(np.argmax(np.where(candidato[i:j], c["amp_norm"][i:j], -1.0)))   # el pico del grupo
        amp = float(c["amp_norm"][k])
        sev = "alta" if amp >= p["severidad_alta_g"] else "media" if amp >= p["severidad_media_g"] else "baja"
        eventos.append({"t_s": round(float(s.t[k]), 3), "lat": None if math.isnan(s.lat[k]) else round(float(s.lat[k]), 7),
                        "lon": None if math.isnan(s.lon[k]) else round(float(s.lon[k]), 7),
                        "vel_kmh": round(float(c["vel"][k]), 1), "pico_g": round(float(c["pico"][k]), 3),
                        "amplitud_norm_g": round(amp, 3), "jerk_g_s": round(float(c["jerk"][k]), 1),
                        "rms_g": round(float(c["rms_local"][k]), 3), "severidad": sev,
                        "confianza": round(float(1 - 1 / max(1.0, m[k])), 3)})
        i = max(j, i + refr)
    return eventos


# ---------------------------------------------------------------- evaluación
def emparejar(eventos: list[dict], etiquetas: list[tuple[float, str]], p: dict) -> dict:
    """Empareja cada marca positiva con el evento más cercano a ± tolerancia (cada evento se usa una vez)."""
    tol, positivas = p["tolerancia_s"], set(p["clases_positivas"])
    marcas = [(t, c) for t, c in etiquetas if c in positivas]
    usados, por_clase = set(), {}
    for t, c in marcas:
        cand = [(abs(e["t_s"] - t), i) for i, e in enumerate(eventos) if i not in usados and abs(e["t_s"] - t) <= tol]
        d = por_clase.setdefault(c, {"marcas": 0, "detectadas": 0})
        d["marcas"] += 1
        if cand:
            usados.add(min(cand)[1])
            d["detectadas"] += 1
    buenas = [t for t, c in etiquetas if c == "via_buena"]
    fp_en_via_buena = sum(1 for i, e in enumerate(eventos) if i not in usados
                          and any(abs(e["t_s"] - t) <= tol for t in buenas))
    tp, fp, fn = len(usados), len(eventos) - len(usados), len(marcas) - len(usados)
    return {"tp": tp, "fp": fp, "fn": fn, "por_clase": por_clase, "fp_en_via_buena": fp_en_via_buena}


def metricas(tp: int, fp: int, fn: int) -> dict:
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else (0.0 if prec is not None and rec is not None else None)
    r = lambda v: None if v is None else round(v, 3)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": r(prec), "exhaustividad": r(rec), "f1": r(f1)}


def evaluar(senales: list[Senal], p: dict) -> dict:
    total = {"tp": 0, "fp": 0, "fn": 0}
    clases: dict[str, dict] = {}
    por_sesion = []
    for s in senales:
        e = emparejar(detectar(s, p), s.etiquetas, p)
        for k in total:
            total[k] += e[k]
        for c, d in e["por_clase"].items():
            x = clases.setdefault(c, {"marcas": 0, "detectadas": 0})
            x["marcas"] += d["marcas"]
            x["detectadas"] += d["detectadas"]
        por_sesion.append({"sesion": s.nombre, **metricas(e["tp"], e["fp"], e["fn"]),
                           "marcas": sum(d["marcas"] for d in e["por_clase"].values())})
    return {"global": metricas(**total), "por_sesion": por_sesion,
            "por_clase": {c: {**d, "exhaustividad": round(d["detectadas"] / d["marcas"], 3) if d["marcas"] else None}
                          for c, d in sorted(clases.items())}}


REJILLA = {"umbral_pico_g": [0.2, 0.3, 0.4, 0.5, 0.7], "umbral_rel_fondo": [2.5, 4.0, 6.0],
           "umbral_jerk_g_s": [5.0, 10.0, 20.0]}


def calibrar(senales: list[Senal], p: dict) -> tuple[dict, dict]:
    """Mejor F1 en la rejilla con las sesiones de entrenamiento; la de prueba nunca participa (sin fugas)."""
    mejor, mejor_f1 = None, -1.0
    for valores in itertools.product(*REJILLA.values()):
        q = {**p, **dict(zip(REJILLA, valores))}
        f1 = evaluar(senales, q)["global"]["f1"] or 0.0
        if f1 > mejor_f1:
            mejor, mejor_f1 = q, f1
    return mejor, {"f1_entrenamiento": round(mejor_f1, 3), **{k: mejor[k] for k in REJILLA}}


def validar_dejando_una_fuera(senales: list[Senal], p: dict) -> dict:
    """Para cada salida: calibrar con las demás y medir en ella. Requiere ≥ 2 sesiones con marcas."""
    con_marcas = [s for s in senales if any(c in p["clases_positivas"] for _, c in s.etiquetas)]
    if len(con_marcas) < 2:
        return {"error": f"Hacen falta ≥ 2 sesiones con marcas; hay {len(con_marcas)}. No se calibra."}
    pliegues, total = [], {"tp": 0, "fp": 0, "fn": 0}
    for i, prueba in enumerate(con_marcas):
        q, info = calibrar([s for j, s in enumerate(con_marcas) if j != i], p)
        e = evaluar([prueba], q)["global"]
        for k in total:
            total[k] += e[k]
        pliegues.append({"prueba": prueba.nombre, **info, **{f"prueba_{k}": e[k] for k in ("precision",
                                                                                          "exhaustividad", "f1")}})
    final, info_final = calibrar(con_marcas, p)
    return {"pliegues": pliegues, "global_prueba": metricas(**total), "parametros_finales": info_final,
            "final": final}


# ---------------------------------------------------------------- informe y CLI
def _informe(titulo: str, datos: dict, p: dict, n_ses: int) -> str:
    l = [f"# {titulo}", "", f"Generado {datetime.now():%Y-%m-%d %H:%M} · detector {p['version']} · {n_ses} sesiones · "
         f"tolerancia ± {p['tolerancia_s']} s", ""]
    g = datos.get("global") or datos.get("global_prueba")
    if "error" in datos:
        return "\n".join(l + [f"**{datos['error']}**", ""])
    l += ["| | TP | FP | FN | Precisión | Exhaustividad | F1 |", "|---|---|---|---|---|---|---|",
          f"| Global | {g['tp']} | {g['fp']} | {g['fn']} | {g['precision']} | {g['exhaustividad']} | {g['f1']} |", ""]
    if "por_clase" in datos:
        l += ["## Por clase (exhaustividad: marcas que el detector encontró)", "", "| Clase | Marcas | Detectadas | "
              "Exhaustividad |", "|---|---|---|---|"]
        l += [f"| {c} | {d['marcas']} | {d['detectadas']} | {d['exhaustividad']} |" for c, d in datos["por_clase"].items()]
        l += ["", "El detector no asigna clase: la precisión por clase y la matriz de confusión entre clases salen del "
              "clasificador de ventanas (`viaviva dataset evaluar`).", ""]
    if "pliegues" in datos:
        l += ["## Validación dejando una salida completa afuera", "", "| Salida de prueba | pico | rel. fondo | jerk | "
              "F1 entr. | P prueba | R prueba | F1 prueba |", "|---|---|---|---|---|---|---|---|"]
        l += [f"| {x['prueba']} | {x['umbral_pico_g']} | {x['umbral_rel_fondo']} | {x['umbral_jerk_g_s']} | "
              f"{x['f1_entrenamiento']} | {x['prueba_precision']} | {x['prueba_exhaustividad']} | {x['prueba_f1']} |"
              for x in datos["pliegues"]]
    n_marcas = sum(d["marcas"] for d in datos.get("por_clase", {}).values()) if "por_clase" in datos else None
    if n_marcas is not None and n_marcas < 30:
        l += ["", f"**Pocos datos ({n_marcas} marcas):** estas cifras no son concluyentes."]
    return "\n".join(l) + "\n"


def main():
    ap = argparse.ArgumentParser(prog="viaviva detector", description="Detector por umbrales calibrable")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nombre in ("detectar", "evaluar", "calibrar"):
        x = sub.add_parser(nombre)
        x.add_argument("sesiones", nargs="+", help="carpetas de sesión, exports .zip o carpetas que los contengan")
        x.add_argument("--config", help="YAML de parámetros (por defecto config/detector_calibrado.yaml o detector.yaml)")
        x.add_argument("--salida", help="carpeta de salida")
    a = ap.parse_args()
    p = cargar_parametros(a.config)
    senales = [cargar(r, p["fs_hz"]) for r in sesiones_en(a.sesiones)]
    salida = Path(a.salida) if a.salida else SALIDAS / datetime.now().strftime("%Y-%m-%d_%H%M")
    salida.mkdir(parents=True, exist_ok=True)
    if a.cmd == "detectar":
        for s in senales:
            ev = detectar(s, p)
            ruta = salida / f"{s.nombre}_eventos.csv"
            with open(ruta, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(ev[0]) if ev else ["t_s"])
                w.writeheader()
                w.writerows(ev)
            sev = {k: sum(1 for e in ev if e["severidad"] == k) for k in ("baja", "media", "alta")}
            print(f"{s.nombre}: {len(ev)} eventos {sev} → {ruta}")
        return 0
    if a.cmd == "evaluar":
        datos, titulo = evaluar(senales, p), "Evaluación del detector (sin calibrar)"
    else:
        datos, titulo = validar_dejando_una_fuera(senales, p), "Calibración del detector"
        if "final" in datos:
            q = copy.deepcopy(datos.pop("final"))
            q["version"] = f"v2-calibrado-{datetime.now():%Y%m%d}"
            RUTA_CALIBRADO.write_text("# Escrito por `viaviva detector calibrar`. Ver informe en data/procesado/detector/\n"
                                      + yaml.safe_dump(q, allow_unicode=True, sort_keys=False), encoding="utf-8")
            print(f"Parámetros calibrados → {RUTA_CALIBRADO}")
    texto = _informe(titulo, datos, p, len(senales))
    (salida / "informe.md").write_text(texto, encoding="utf-8")
    (salida / "informe.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(texto)
    print(f"→ {salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
