"""Cadena completa de entrenamiento del detector, en UN comando.

  recorridos etiquetados (phyphox y/o nodo) → ventanas → características → bosque (emlearn) y red 1D
  → int8 → exportación a C para el ESP32 → validación leave-one-drive-out → comparación con el detector por umbrales

Uso (desde via-viva/):
  analysis\\.venv\\Scripts\\python analysis\\entrenar_detector.py                # datos reales de data/raw/
  analysis\\.venv\\Scripts\\python analysis\\entrenar_detector.py --sintetico    # prueba con recorridos SINTÉTICOS

Datos reales:
  data/raw/phyphox/<recorrido>(.zip|/|.csv) + <recorrido>_etiquetas.csv   (protocolo en analysis/README.md)
  data/raw/nodo/<sesion>/crudo_NNN.csv, gps_NNN.csv, etiquetas_NNN.csv    (copiados de la microSD del nodo)
Si no hay al menos 2 recorridos etiquetados, el script se detiene, salvo que se pida --sintetico.

Salidas:
  analysis/salidas/detector_<fecha>[_SINTETICO].md y .json   métricas (ignorado por Git)
  firmware/nodo-sensores/src/modelo_cnn.h                      red 1D float32 + int8 (para E2/E3 y el nodo)
  firmware/nodo-sensores/src/modelo_bosque.h                   bosque exportado con emlearn
Con --sintetico los modelos llevan MODELO_SINTETICO 1: sirven para medir latencia (E2/E3), NO para detectar huecos.

Coherencia con el nodo: la señal es |a| − 1 g a 200 Hz (lo mismo que calcula procesamiento.cpp), las características
son las de src/caracteristicas.h y las ventanas se cortan alrededor del disparo del detector por umbrales.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix, f1_score

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from analysis import modelo_cnn, senales  # noqa: E402
from analysis.detector_umbral import ParametrosUmbral, detectar_umbral  # noqa: E402

FS = 200.0
PRE, POST = 300, 100          # ventana de características: 1,5 s antes y 0,5 s después del disparo (400 muestras)
MEDIO_CNN = modelo_cnn.L_ENTRADA // 2
TOLERANCIA_S = 1.0
CLASES = modelo_cnn.CLASES
CLASES_VIA = {"hueco", "resalto", "impacto_fuerte"}
NOMBRES_CARACT = ["pico_g", "rms_g", "curtosis", "factor_cresta", "jerk_max_gps", "signo_pico", "vel_kmh"]
ARBOLES, PROFUNDIDAD = 10, 6
FIRMWARE = RAIZ / "firmware" / "nodo-sensores" / "src"
SALIDAS = Path(__file__).resolve().parent / "salidas"


# ============================================================================
# 1. Recorridos → señal |a| - 1 g a 200 Hz, velocidad y etiquetas
# ============================================================================
def _a_rejilla(t, ax, ay, az, en_g: bool):
    tu = np.arange(t[0], t[-1], 1 / FS)
    a = np.sqrt(np.interp(tu, t, ax) ** 2 + np.interp(tu, t, ay) ** 2 + np.interp(tu, t, az) ** 2)
    return tu, (a if en_g else a / senales.G) - 1.0


def _recorrido(nombre, origen, t, a, gps_t, gps_vel_ms, etiquetas) -> dict:
    vel = np.interp(t, gps_t, gps_vel_ms) * 3.6 if len(gps_t) > 1 else np.zeros_like(t)
    dist_km = float(np.trapezoid(vel / 3.6, t) / 1000)
    return {"nombre": nombre, "origen": origen, "t": t, "a": a.astype(np.float32), "vel": vel, "dist_km": dist_km,
            "etiquetas": etiquetas}


def cargar_phyphox(carpeta: Path) -> list[dict]:
    salida = []
    if not carpeta.exists():
        return salida
    for p in sorted(carpeta.glob("*")):
        if p.name.endswith("_etiquetas.csv") or p.name.startswith("_") or not (p.is_dir() or p.suffix in (".zip", ".csv")):
            continue
        base = p.with_suffix("") if p.suffix else p
        ruta_et = base.parent / f"{base.name}_etiquetas.csv"
        if not ruta_et.exists():
            continue
        d = senales.cargar_phyphox_completo(p)
        if d["gps"] is None:
            continue
        acc = d["acc"]
        t, a = _a_rejilla(acc["t"].to_numpy(), acc["ax"].to_numpy(), acc["ay"].to_numpy(), acc["az"].to_numpy(), False)
        if not acc.attrs.get("con_g", True):
            a = a + 1.0   # aceleración sin g: la magnitud ya es la dinámica
        et = pd.read_csv(ruta_et, sep=None, engine="python")
        et.columns = [c.strip().lower() for c in et.columns]
        salida.append(_recorrido(base.name, "phyphox", t, a, d["gps"]["t"].to_numpy(),
                                 d["gps"]["vel"].fillna(0).to_numpy(), et[["t_s", "clase"]]))
    return salida


def cargar_nodo(carpeta: Path) -> list[dict]:
    """Sesiones copiadas de la microSD: crudo (cuentas de 3,9 mg), gps y etiquetas con t_us del nodo."""
    salida = []
    if not carpeta.exists():
        return salida
    for crudo in sorted(carpeta.rglob("crudo_*.csv")):
        n = crudo.stem.split("_")[1]
        r_gps, r_et = crudo.with_name(f"gps_{n}.csv"), crudo.with_name(f"etiquetas_{n}.csv")
        if not (r_gps.exists() and r_et.exists()):
            continue
        c = pd.read_csv(crudo)
        g = pd.read_csv(r_gps)
        e = pd.read_csv(r_et)
        t0 = c["t_us"].iloc[0]
        t, a = _a_rejilla(((c["t_us"] - t0) / 1e6).to_numpy(), *(c[k].to_numpy() * 0.0039 for k in ("ax", "ay", "az")), True)
        et = pd.DataFrame({"t_s": (e["t_us"] - t0) / 1e6, "clase": e["tipo"].str.strip().str.lower()})
        salida.append(_recorrido(f"nodo_{crudo.parent.name}_{n}", "nodo", t, a, ((g["t_us"] - t0) / 1e6).to_numpy(),
                                 (g["vel_kmh"] / 3.6).to_numpy(), et))
    return salida


def cargar_sintetico(n: int = 6) -> list[dict]:
    salida = []
    for i in range(n):
        acc, gps, et = senales.recorrido_sintetico(f"s{i}", semilla=100 + i)
        t, a = _a_rejilla(acc["t"].to_numpy(), acc["ax"].to_numpy(), acc["ay"].to_numpy(), acc["az"].to_numpy(), False)
        salida.append(_recorrido(f"SINTETICO_{i + 1}", "sintetico", t, a, gps["t"].to_numpy(), gps["vel"].to_numpy(), et))
    return salida


# ============================================================================
# 2. Ventanas y características (idénticas a las del nodo)
# ============================================================================
def caracteristicas_nodo(w: np.ndarray, vel_kmh: float) -> list[float]:
    """Réplica de calcularCaracteristicas() de src/caracteristicas.h, más la velocidad."""
    w = w.astype(np.float64)
    media = w.mean()
    m2 = np.mean((w - media) ** 2)
    m4 = np.mean((w - media) ** 4)
    i = int(np.argmax(np.abs(w)))
    pico = abs(w[i])
    rms = np.sqrt(np.mean(w ** 2))
    return [pico, rms, m4 / (m2 * m2) if m2 > 1e-12 else 0.0, pico / rms if rms > 1e-6 else 0.0,
            float(np.max(np.abs(np.diff(w))) * FS), -1.0 if w[i] < 0 else 1.0, vel_kmh]


def ventanas(rec: dict, pu: ParametrosUmbral, semilla: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (ventanas, candidatos). Ventanas: anclaje, clase, características, entrada de la red."""
    a, t, vel = rec["a"], rec["t"], rec["vel"]
    cand = detectar_umbral(a, vel, FS, pu)
    cand["t_s"] = t[cand["indice"]] if len(cand) else []
    et = rec["etiquetas"].copy()
    et["clase"] = et["clase"].astype(str).str.strip().str.lower()
    usados, filas = set(), []
    for _, e in et.iterrows():
        cerca = cand[(cand["t_s"] - e["t_s"]).abs() <= TOLERANCIA_S] if len(cand) else cand
        if len(cerca):                                   # anclar en el disparo, como en el nodo
            k = int((cerca["t_s"] - e["t_s"]).abs().idxmin())
            usados.add(k)
            anc = int(cand.loc[k, "indice"])
        else:                                            # el detector no lo vio: anclar en el pico
            i0 = int(np.searchsorted(t, e["t_s"] - TOLERANCIA_S))
            i1 = int(np.searchsorted(t, e["t_s"] + TOLERANCIA_S))
            if i1 <= i0:
                continue
            anc = i0 + int(np.argmax(np.abs(a[i0:i1])))
        if e["clase"] in CLASES_VIA:
            filas.append((anc, e["clase"], "etiqueta"))
    for k, c in cand.iterrows():                         # disparos sin etiqueta: falsas alarmas (negativos difíciles)
        if k not in usados:
            filas.append((int(c["indice"]), "normal", "falsa_alarma"))
    rng = np.random.default_rng(semilla)
    marcas = np.array([f[0] for f in filas] + [int(np.searchsorted(t, s)) for s in et["t_s"]])
    n_norm = max(5, sum(1 for f in filas if f[1] != "normal"))
    for _ in range(50 * n_norm):
        if n_norm == 0:
            break
        i = int(rng.integers(PRE, len(a) - POST))
        if marcas.size and np.min(np.abs(marcas - i)) < 2 * FS:
            continue
        filas.append((i, "normal", "azar"))
        marcas = np.append(marcas, i)
        n_norm -= 1
    salida = []
    for anc, clase, fuente in filas:
        if anc - PRE + 1 < 0 or anc + POST >= len(a) or anc - MEDIO_CNN < 0 or anc + MEDIO_CNN > len(a):
            continue
        salida.append({"recorrido": rec["nombre"], "indice": anc, "t_s": t[anc], "clase": clase, "fuente": fuente,
                       "x": caracteristicas_nodo(a[anc - PRE + 1:anc + POST + 1], float(vel[anc])),
                       "cnn": a[anc - MEDIO_CNN:anc + MEDIO_CNN].copy()})
    return pd.DataFrame(salida), cand


# ============================================================================
# 3. Modelos
# ============================================================================
def entrenar_bosque(X, y, semilla=0):
    return RandomForestClassifier(n_estimators=ARBOLES, max_depth=PROFUNDIDAD, class_weight="balanced",
                                  random_state=semilla).fit(X, y)


def a_indices(clases):
    return np.array([CLASES.index(c) for c in clases])


def eventos_metricas(cand_t, cand_pred, et: pd.DataFrame, dist_km: float, solo: str | None = None) -> dict:
    """Métricas por evento: un disparo es acierto si hay una etiqueta de la vía a ≤ 1 s (y de la misma clase si solo=...)."""
    ref = et[et["clase"].isin(CLASES_VIA if solo is None else {solo})]["t_s"].to_numpy()
    pred_t = np.array([t for t, p in zip(cand_t, cand_pred) if p != "normal" and (solo is None or p == solo)])
    tp_pred = sum(1 for t in pred_t if ref.size and np.min(np.abs(ref - t)) <= TOLERANCIA_S)
    tp_ref = sum(1 for t in ref if pred_t.size and np.min(np.abs(pred_t - t)) <= TOLERANCIA_S)
    return {"predichos": int(pred_t.size), "reales": int(ref.size), "acierto_pred": tp_pred, "acierto_real": tp_ref,
            "falsos": int(pred_t.size - tp_pred), "km": dist_km}


def resumir(lista: list[dict]) -> dict:
    s = {k: sum(d[k] for d in lista) for k in ("predichos", "reales", "acierto_pred", "acierto_real", "falsos", "km")}
    p = s["acierto_pred"] / s["predichos"] if s["predichos"] else 0.0
    r = s["acierto_real"] / s["reales"] if s["reales"] else 0.0
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0,
            "falsos_por_km": s["falsos"] / s["km"] if s["km"] else float("nan"), **s}


def lodo(recs, V, cands, semilla=0) -> dict:
    """Leave-one-drive-out: cada recorrido se evalúa con modelos entrenados SOLO con los otros."""
    pred = {"bosque": [], "cnn_f32": [], "cnn_i8": []}
    reales, coinciden_i8 = [], 0
    ev = {k: [] for k in ("umbral", "umbral+bosque", "umbral+cnn_i8")}
    ev_hueco = {k: [] for k in ev}
    for rec in recs:
        prueba = V[V["recorrido"] == rec["nombre"]]
        entren = V[V["recorrido"] != rec["nombre"]]
        if prueba.empty or entren["clase"].nunique() < 2:
            continue
        bosque = entrenar_bosque(np.stack(entren["x"]), entren["clase"], semilla)
        Xc = np.stack(entren["cnn"])
        P = modelo_cnn.entrenar(Xc, a_indices(entren["clase"]), semilla=semilla)
        Q = modelo_cnn.cuantizar(P, Xc)
        pb = bosque.predict(np.stack(prueba["x"]))
        pf = [CLASES[int(np.argmax(modelo_cnn.inferir_f32(P, x)))] for x in prueba["cnn"]]
        pq = [CLASES[int(np.argmax(modelo_cnn.inferir_i8(Q, x)))] for x in prueba["cnn"]]
        reales += list(prueba["clase"])
        pred["bosque"] += list(pb)
        pred["cnn_f32"] += pf
        pred["cnn_i8"] += pq
        coinciden_i8 += sum(a == b for a, b in zip(pf, pq))
        # Por evento, sobre TODOS los disparos del detector en el recorrido de prueba
        cand = cands[rec["nombre"]]
        a = rec["a"]
        ok = [(int(i), t) for i, t in zip(cand["indice"], cand["t_s"])
              if i - PRE + 1 >= 0 and i + POST < len(a) and i - MEDIO_CNN >= 0 and i + MEDIO_CNN <= len(a)]
        tiempos = [t for _, t in ok]
        regla = ["hueco" if a[i] < 0 else "resalto" for i, _ in ok]   # umbral solo: clase por el signo del golpe
        xb = [caracteristicas_nodo(a[i - PRE + 1:i + POST + 1], float(rec["vel"][i])) for i, _ in ok]
        cb = list(bosque.predict(np.stack(xb))) if xb else []
        cq = [CLASES[int(np.argmax(modelo_cnn.inferir_i8(Q, a[i - MEDIO_CNN:i + MEDIO_CNN])))] for i, _ in ok]
        for nombre, p in (("umbral", regla), ("umbral+bosque", cb), ("umbral+cnn_i8", cq)):
            ev[nombre].append(eventos_metricas(tiempos, p, rec["etiquetas"], rec["dist_km"]))
            ev_hueco[nombre].append(eventos_metricas(tiempos, p, rec["etiquetas"], rec["dist_km"], solo="hueco"))
    etiquetas = [c for c in CLASES if c in set(reales)]
    ventana = {}
    for nombre, p in pred.items():
        ventana[nombre] = {
            "f1_macro": f1_score(reales, p, average="macro", labels=etiquetas, zero_division=0),
            "f1_hueco": f1_score(reales, p, labels=["hueco"], average="macro", zero_division=0),
            "confusion": confusion_matrix(reales, p, labels=etiquetas).tolist()}
    return {"ventanas": ventana, "clases": etiquetas, "n_ventanas": len(reales),
            "coincidencia_f32_i8": coinciden_i8 / len(reales) if reales else float("nan"),
            "eventos": {k: resumir(v) for k, v in ev.items()},
            "eventos_hueco": {k: resumir(v) for k, v in ev_hueco.items()}}


# ============================================================================
# 4. Exportación
# ============================================================================
def exportar(V, sintetico: bool, fuentes: str, semilla=0) -> dict:
    import emlearn
    X, y = np.stack(V["x"]), V["clase"]
    bosque = entrenar_bosque(X, a_indices(y), semilla)       # índices de clase para que el C devuelva 0..3
    Xc = np.stack(V["cnn"])
    P = modelo_cnn.entrenar(Xc, a_indices(y), semilla=semilla)
    Q = modelo_cnn.cuantizar(P, Xc)
    aviso = ("DATOS SINTÉTICOS: este modelo sirve para medir latencia (E2/E3), NO para detectar huecos reales."
             if sintetico else f"Entrenado con: {fuentes}")
    enc = (f"modelo_cnn.h — GENERADO por analysis/entrenar_detector.py el {date.today().isoformat()}. NO editar a mano.\n"
           f"{aviso}\nEntrada: 128 muestras de |a| - 1 g a 200 Hz centradas en el disparo del detector por umbrales.")
    modelo_cnn.exportar_c(P, Q, FIRMWARE / "modelo_cnn.h", enc)
    with open(FIRMWARE / "modelo_cnn.h", "a", encoding="utf-8") as f:
        f.write(f"\n#define MODELO_SINTETICO {1 if sintetico else 0}\n")
    ruta_b = FIRMWARE / "modelo_bosque.h"
    emlearn.convert(bosque, method="inline", dtype="float").save(file=str(ruta_b), name="bosque")
    texto = ruta_b.read_text(encoding="utf-8")
    ruta_b.write_text(f"// modelo_bosque.h — GENERADO por analysis/entrenar_detector.py el {date.today().isoformat()} "
                      f"con emlearn. NO editar.\n// {aviso}\n// Entradas (float, en este orden): "
                      f"{', '.join(NOMBRES_CARACT)}. Salida: {', '.join(CLASES)}.\n"
                      f"#pragma once\n#define BOSQUE_SINTETICO {1 if sintetico else 0}\n" + texto, encoding="utf-8")
    # comprobación: Python float vs. int8 en todas las ventanas
    pf = np.array([np.argmax(modelo_cnn.inferir_f32(P, x)) for x in Xc])
    pq = np.array([np.argmax(modelo_cnn.inferir_i8(Q, x)) for x in Xc])
    return {"parametros_cnn": int(sum(v.size for v in P.values())),
            "bytes_cnn_f32": int(sum(v.size for v in P.values()) * 4),
            "bytes_cnn_i8": int(sum(Q[k].size for k in ("w1", "w2", "w3")) + 4 * sum(Q[k].size for k in ("b1", "b2", "b3"))),
            "nodos_bosque": int(sum(e.tree_.node_count for e in bosque.estimators_)),
            "coincidencia_f32_i8_entrenamiento": float(np.mean(pf == pq))}


# ============================================================================
def informe(res: dict, meta: dict, ruta_md: Path):
    sint = meta["sintetico"]
    L = [f"# Detector de VÍA VIVA — entrenamiento del {meta['fecha']}", ""]
    if sint:
        L += ["> **DATOS SINTÉTICOS.** Estas métricas solo prueban que la cadena funciona. **No son resultados** y no "
              "van al informe.", ""]
    L += [f"Recorridos: {meta['n_recorridos']} ({meta['fuentes']}), {meta['km']:.1f} km · ventanas: {res['n_ventanas']} · "
          f"validación leave-one-drive-out.", "", "## Clasificación de ventanas", "",
          "| Modelo | F1 macro | F1 hueco |", "|---|---|---|"]
    for k, v in res["ventanas"].items():
        L.append(f"| {k} | {v['f1_macro']:.3f} | {v['f1_hueco']:.3f} |")
    L += ["", f"Coincidencia float32 vs. int8 en las ventanas de prueba: {res['coincidencia_f32_i8'] * 100:.1f} %", "",
          "## Por evento (todos los disparos del detector por umbrales)", "",
          "| Cadena | Precisión | Recall | F1 | Falsos/km | Precisión hueco | Recall hueco | F1 hueco |",
          "|---|---|---|---|---|---|---|---|"]
    for k, v in res["eventos"].items():
        h = res["eventos_hueco"][k]
        L.append(f"| {k} | {v['precision']:.3f} | {v['recall']:.3f} | {v['f1']:.3f} | {v['falsos_por_km']:.2f} | "
                 f"{h['precision']:.3f} | {h['recall']:.3f} | {h['f1']:.3f} |")
    L += ["", "`umbral` = detector por umbrales solo (clase por el signo del golpe). Los otros clasifican cada disparo.", "",
          "## Modelos exportados", "", f"- Red 1D: {meta['export']['parametros_cnn']} parámetros, "
          f"{meta['export']['bytes_cnn_f32']} B en float32 y {meta['export']['bytes_cnn_i8']} B en int8 "
          "(`firmware/nodo-sensores/src/modelo_cnn.h`).",
          f"- Bosque: {ARBOLES} árboles, profundidad ≤ {PROFUNDIDAD}, {meta['export']['nodos_bosque']} nodos "
          "(`firmware/nodo-sensores/src/modelo_bosque.h`).",
          f"- Coincidencia float32 vs. int8 (entrenamiento completo): "
          f"{meta['export']['coincidencia_f32_i8_entrenamiento'] * 100:.1f} %.", "",
          f"Parámetros del detector por umbrales: {meta['umbral']}"]
    ruta_md.write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sintetico", action="store_true", help="usa recorridos SINTÉTICOS (prueba de la cadena)")
    ap.add_argument("--phyphox", default=str(RAIZ / "data" / "raw" / "phyphox"))
    ap.add_argument("--nodo", default=str(RAIZ / "data" / "raw" / "nodo"))
    ap.add_argument("--no-exportar", action="store_true")
    args = ap.parse_args()

    recs = cargar_sintetico() if args.sintetico else cargar_phyphox(Path(args.phyphox)) + cargar_nodo(Path(args.nodo))
    if len(recs) < 2:
        raise SystemExit(f"Hay {len(recs)} recorridos etiquetados (se necesitan ≥ 2 para leave-one-drive-out). "
                         "Ver el protocolo en analysis/README.md, o probar la cadena con --sintetico.")
    pu = ParametrosUmbral()
    tablas, cands = [], {}
    for i, r in enumerate(recs):
        v, c = ventanas(r, pu, semilla=i)
        tablas.append(v)
        cands[r["nombre"]] = c
    V = pd.concat(tablas, ignore_index=True)
    fuentes = ", ".join(sorted({r["origen"] for r in recs}))
    print(f"{len(recs)} recorridos ({fuentes}), {V.shape[0]} ventanas: {V['clase'].value_counts().to_dict()}")
    if args.sintetico:
        print("*** DATOS SINTÉTICOS: las métricas solo prueban la cadena; NO son resultados ***")
    res = lodo(recs, V, cands)
    meta = {"fecha": date.today().isoformat(), "sintetico": args.sintetico, "fuentes": fuentes, "n_recorridos": len(recs),
            "recorridos": [r["nombre"] for r in recs], "km": sum(r["dist_km"] for r in recs), "umbral": vars(pu)}
    meta["export"] = {} if args.no_exportar else exportar(V, args.sintetico, fuentes)
    SALIDAS.mkdir(exist_ok=True)
    nombre = f"detector_{meta['fecha']}{'_SINTETICO' if args.sintetico else ''}"
    (SALIDAS / f"{nombre}.json").write_text(json.dumps({"meta": meta, "resultados": res}, indent=2, ensure_ascii=False,
                                                       default=float), encoding="utf-8")
    if meta["export"]:
        informe(res, meta, SALIDAS / f"{nombre}.md")
        print((SALIDAS / f"{nombre}.md").read_text(encoding="utf-8"))
    print(f"Guardado: {SALIDAS / nombre}.json")


if __name__ == "__main__":
    main()
