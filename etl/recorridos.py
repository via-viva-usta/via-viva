"""Recorridos de phyphox → pre-etiquetas, tramos revisados y eventos confirmados.

Entrada: data/raw/phyphox/ (una entrada por recorrido; formato en analysis/README.md)
  <recorrido>.zip | <recorrido>/ | <recorrido>.csv   export de phyphox con acelerómetro (con g), giroscopio y GPS
  <recorrido>_etiquetas.csv                          lo que anotó el copiloto: t_s,clase

Qué hace por recorrido:
  1. Remuestrea el acelerómetro, saca la aceleración vertical y aplica el DETECTOR POR UMBRALES
     (analysis/detector_umbral.py, la misma regla del firmware) → candidatos a evento.
  2. Detecta maniobras con el giroscopio (giro izquierda/derecha) y el GPS (frenada brusca).
  3. Asigna cada fijación GPS, cada candidato y cada etiqueta al tramo de OSM más cercano (≤ 25 m: map-matching
     por vecino más cercano). La trayectoria NO se guarda: solo qué tramos se recorrieron.
  4. Un tramo cuenta como REVISADO si el recorrido cubrió ≥ 50 % de su largo (o tocó un tramo de < 30 m).

Salidas (data/campo/, ignorada por Git):
  preetiquetas_<recorrido>.csv  candidatos del detector, con la etiqueta del copiloto al lado (para revisar)
  tramos_revisados.csv          id_tramo, tiene_hueco, ... ← entrada del modelo de riesgo (plan B)
y en la base: los huecos/resaltos ETIQUETADOS por el copiloto como eventos con origen='phyphox'.

Qué etiqueta lleva cada tramo revisado:
  * recorrido con _etiquetas.csv → tiene_hueco = 1 si el copiloto marcó un hueco en ese tramo, si no 0
    (fuente 'recorrido_etiquetado');
  * recorrido sin etiquetas → solo entra si se usa --usar-preetiquetas: tiene_hueco = 1 si el detector
    disparó (fuera de maniobras) en el tramo (fuente 'preetiqueta_umbral', de menor calidad).

Uso (desde via-viva/):
  etl\\.venv\\Scripts\\python -m etl.recorridos
  etl\\.venv\\Scripts\\python -m etl.recorridos --carpeta data/raw/phyphox_sintetico --salida data/campo/sintetico --sin-base
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from etl.config import DATA, RAIZ
from etl.db import ahora_utc, conectar
from etl.geohash import codificar

sys.path.insert(0, str(RAIZ))
from analysis import senales  # noqa: E402
from analysis.detector_umbral import (ParametrosManiobra, ParametrosUmbral, detectar_maniobras,  # noqa: E402
                                      detectar_umbral, giro_vertical, parametros_como_texto)
from risk_model.variables import CRS_METROS, leer_tramos  # noqa: E402

MAX_DIST_M = 25.0
COBERTURA_MIN = 0.5
TRAMO_CORTO_M = 30.0
TOLERANCIA_ETIQUETA_S = 1.0
CLASES_VIA = {"hueco", "resalto", "impacto_fuerte", "obstaculo"}


def entradas(carpeta: Path) -> list[Path]:
    return [p for p in sorted(carpeta.glob("*")) if not p.name.endswith("_etiquetas.csv")
            and not p.name.startswith("_") and (p.is_dir() or p.suffix.lower() in (".csv", ".zip"))]


def leer_etiquetas(p: Path) -> pd.DataFrame | None:
    base = p.with_suffix("") if p.suffix else p
    ruta = base.parent / f"{base.name}_etiquetas.csv"
    if not ruta.exists():
        return None
    df = pd.read_csv(ruta, sep=None, engine="python")
    df.columns = [c.strip().lower() for c in df.columns]
    df["clase"] = df["clase"].astype(str).str.strip().str.lower()
    return df[["t_s", "clase"]]


def inicio_utc(p: Path) -> datetime:
    """Hora de inicio: meta/time.csv del export de phyphox; si no existe, la fecha del archivo (aproximada)."""
    meta = None
    if p.is_dir() and (p / "meta" / "time.csv").exists():
        meta = pd.read_csv(p / "meta" / "time.csv", sep=None, engine="python")
    elif p.suffix.lower() == ".zip":
        import zipfile
        with zipfile.ZipFile(p) as z:
            if "meta/time.csv" in z.namelist():
                meta = pd.read_csv(z.open("meta/time.csv"), sep=None, engine="python")
    if meta is not None:
        cols = {c.lower(): c for c in meta.columns}
        col_sis = next((cols[c] for c in cols if c.startswith("system time") and "text" not in c), None)
        if col_sis is not None:
            return datetime.fromtimestamp(float(meta[col_sis].iloc[0]), tz=timezone.utc)
    return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)


def velocidad_kmh(gps: pd.DataFrame) -> pd.Series:
    """Velocidad del GPS; si phyphox no la trae, se calcula con la distancia entre fijaciones."""
    if gps["vel"].notna().sum() > len(gps) / 2:
        return gps["vel"].fillna(0) * 3.6
    lat, lon = np.radians(gps["lat"].to_numpy()), np.radians(gps["lon"].to_numpy())
    d = 6371000 * np.sqrt((np.diff(lat)) ** 2 + (np.diff(lon) * np.cos(lat[:-1])) ** 2)
    dt = np.diff(gps["t"].to_numpy())
    v = np.r_[0, np.where(dt > 0, d / dt, 0)]
    return pd.Series(v * 3.6, index=gps.index)


def asignar(puntos: pd.DataFrame, tramos: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    g = gpd.GeoDataFrame(puntos.copy(), geometry=gpd.points_from_xy(puntos["lon"], puntos["lat"]),
                         crs="EPSG:4326").to_crs(CRS_METROS)
    j = gpd.sjoin_nearest(g, tramos[["id_tramo", "longitud_m", "geometry"]], how="left",
                          max_distance=MAX_DIST_M, distance_col="dist_m")
    return j[~j.index.duplicated()]


def procesar(p: Path, tramos: gpd.GeoDataFrame, pu: ParametrosUmbral, pm: ParametrosManiobra) -> dict:
    d = senales.cargar_phyphox_completo(p)
    acc, giro, gps = d["acc"], d["giro"], d["gps"]
    if gps is None or len(gps) < 5:
        raise ValueError("sin GPS: no se puede asignar a tramos")
    etiquetas = leer_etiquetas(p)
    fs = min(200.0, float(round(senales.tasa_nativa(acc["t"].to_numpy()))))
    acc_u = senales.remuestrear(acc, fs)
    t = acc_u["t"].to_numpy()
    a_g = senales.pasa_bajos(senales.eje_vertical(acc_u, fs, acc.attrs.get("con_g", True)), fs,
                             min(80.0, 0.4 * fs)) / senales.G
    gps = gps.assign(vel_kmh=velocidad_kmh(gps)).sort_values("t")
    vel = np.interp(t, gps["t"], gps["vel_kmh"])

    # 1) detector por umbrales
    cand = detectar_umbral(a_g, vel, fs, pu)
    # 2) maniobras (giroscopio + caída de velocidad GPS)
    decel = np.interp(t, gps["t"].to_numpy()[1:], -np.diff(gps["vel_kmh"]) / 3.6 / np.maximum(np.diff(gps["t"]), 1e-3)) \
        if len(gps) > 2 else np.zeros_like(t)
    if giro is not None and len(giro) > 10:
        g_u = np.column_stack([np.interp(t, giro["t"], giro[c]) for c in ("gx", "gy", "gz")])
        giro_dps = giro_vertical(acc_u[["ax", "ay", "az"]].to_numpy(), g_u, fs)
    else:
        giro_dps = np.zeros_like(t)
    maniobras = detectar_maniobras(giro_dps, vel, fs, decel, pm)

    filas = []
    medio = int(0.25 * fs)
    for _, c in cand.iterrows():
        i = int(c["indice"])
        en = maniobras[(maniobras["inicio"] <= i) & (maniobras["fin"] >= i)]
        seg = a_g[max(0, i - medio):i + medio]
        sugerida = en["tipo"].iloc[0] if len(en) else ("hueco" if seg[np.argmax(np.abs(seg))] < 0 else "resalto")
        filas.append({"t_s": t[i], "vel_kmh": vel[i], "p2p_g": c["p2p_g"], "razon": c["razon"],
                      "maniobra": en["tipo"].iloc[0] if len(en) else "", "clase_sugerida": sugerida})
    pre = pd.DataFrame(filas, columns=["t_s", "vel_kmh", "p2p_g", "razon", "maniobra", "clase_sugerida"])
    pre["lat"] = np.interp(pre["t_s"], gps["t"], gps["lat"]) if len(pre) else []
    pre["lon"] = np.interp(pre["t_s"], gps["t"], gps["lon"]) if len(pre) else []
    pre["etiqueta_copiloto"] = ""
    if etiquetas is not None and len(pre):
        for _, e in etiquetas.iterrows():
            dist = (pre["t_s"] - e["t_s"]).abs()
            if dist.min() <= TOLERANCIA_ETIQUETA_S:
                pre.loc[dist.idxmin(), "etiqueta_copiloto"] = e["clase"]

    # 3) map-matching de fijaciones, candidatos y etiquetas
    fij = asignar(gps[["t", "lat", "lon"]], tramos)
    geom_de = dict(zip(tramos["id_tramo"], tramos.geometry))   # tabla hash id → geometría
    fij["avance_m"] = [geom_de[int(idt)].project(geom) if pd.notna(idt) else np.nan
                       for idt, geom in zip(fij["id_tramo"], fij.geometry)]
    cob = fij.dropna(subset=["id_tramo"]).groupby("id_tramo").agg(
        n_puntos=("t", "size"), desde=("avance_m", "min"), hasta=("avance_m", "max"), largo=("longitud_m", "first"))
    cob["cobertura"] = ((cob["hasta"] - cob["desde"]) / cob["largo"]).clip(0, 1)
    revisados = cob[(cob["cobertura"] >= COBERTURA_MIN) | (cob["largo"] < TRAMO_CORTO_M)].copy()
    revisados.index = revisados.index.astype(int)

    pre_a = asignar(pre, tramos) if len(pre) else pre.assign(id_tramo=np.nan, dist_m=np.nan)
    et_a = None
    if etiquetas is not None and len(etiquetas):
        et_pos = etiquetas.assign(lat=np.interp(etiquetas["t_s"], gps["t"], gps["lat"]),
                                  lon=np.interp(etiquetas["t_s"], gps["t"], gps["lon"]),
                                  vel_kmh=np.interp(etiquetas["t_s"], gps["t"], gps["vel_kmh"]))
        et_a = asignar(et_pos, tramos)
    return {"nombre": p.stem, "fs": fs, "pre": pre_a, "maniobras": maniobras, "revisados": revisados,
            "etiquetas": et_a, "etiquetado": etiquetas is not None, "inicio": inicio_utc(p),
            "n_fijaciones": len(gps), "fijaciones_en_tramo": int(fij["id_tramo"].notna().sum())}


def tramos_revisados(resultados: list[dict], usar_preetiquetas: bool) -> pd.DataFrame:
    filas = []
    for r in resultados:
        if r["etiquetado"]:
            fuente = "recorrido_etiquetado"
            huecos = r["etiquetas"][r["etiquetas"]["clase"] == "hueco"] if r["etiquetas"] is not None else None
        elif usar_preetiquetas:
            fuente = "preetiqueta_umbral"
            huecos = r["pre"][(r["pre"]["maniobra"] == "") & (r["pre"]["clase_sugerida"] == "hueco")]
        else:
            continue
        conteo = huecos.dropna(subset=["id_tramo"]).groupby("id_tramo").size() if huecos is not None else pd.Series(dtype=int)
        for idt, fila in r["revisados"].iterrows():
            n = int(conteo.get(idt, 0))
            filas.append({"id_tramo": int(idt), "tiene_hueco": int(n > 0), "n_huecos": n,
                          "cobertura": round(float(fila["cobertura"]), 2), "fuente": fuente, "recorrido": r["nombre"]})
        # Un hueco etiquetado en un tramo poco cubierto también lo marca como revisado con hueco
        for idt, n in conteo.items():
            if int(idt) not in r["revisados"].index:
                filas.append({"id_tramo": int(idt), "tiene_hueco": 1, "n_huecos": int(n), "cobertura": np.nan,
                              "fuente": fuente, "recorrido": r["nombre"]})
    if not filas:
        return pd.DataFrame(columns=["id_tramo", "tiene_hueco", "n_huecos", "n_recorridos", "cobertura_max",
                                     "fuente", "recorridos"])
    df = pd.DataFrame(filas)
    return df.groupby("id_tramo").agg(
        tiene_hueco=("tiene_hueco", "max"), n_huecos=("n_huecos", "sum"), n_recorridos=("recorrido", "nunique"),
        cobertura_max=("cobertura", "max"), fuente=("fuente", lambda s: ";".join(sorted(set(s)))),
        recorridos=("recorrido", lambda s: ";".join(sorted(set(s))))).reset_index()


def guardar_eventos(con, r: dict, origen: str) -> int:
    """Huecos/resaltos etiquetados por el copiloto → tabla eventos (sin trayectoria)."""
    if r["etiquetas"] is None:
        return 0
    filas = []
    for _, e in r["etiquetas"].iterrows():
        if e["clase"] not in CLASES_VIA:
            continue
        ts = (r["inicio"] + timedelta(seconds=float(e["t_s"]))).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        filas.append((f"{origen}:{r['nombre']}", ts, float(e["lat"]), float(e["lon"]), float(e["vel_kmh"]),
                      e["clase"], e["clase"], None if pd.isna(e["id_tramo"]) else int(e["id_tramo"]),
                      codificar(float(e["lat"]), float(e["lon"]), 7), ahora_utc(), origen))
    with con:
        con.executemany(
            "INSERT OR IGNORE INTO eventos (id_nodo, ts_utc, lat, lon, velocidad_kmh, clase, etiqueta_manual, "
            "id_tramo, geohash7, ts_carga, origen) VALUES (?,?,?,?,?,?,?,?,?,?,?)", filas)
    return len(filas)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--carpeta", default=str(DATA / "raw" / "phyphox"))
    ap.add_argument("--salida", default=str(DATA / "campo"))
    ap.add_argument("--usar-preetiquetas", action="store_true",
                    help="recorridos sin _etiquetas.csv aportan tramos revisados según el detector (menor calidad)")
    ap.add_argument("--sin-base", action="store_true", help="no escribe eventos en la base")
    ap.add_argument("--origen", default="phyphox", choices=["phyphox", "simulado"])
    args = ap.parse_args()

    carpeta, salida = Path(args.carpeta), Path(args.salida)
    lista = entradas(carpeta) if carpeta.exists() else []
    if not lista:
        raise SystemExit(f"No hay recorridos en {carpeta}. Formato: analysis/README.md")
    salida.mkdir(parents=True, exist_ok=True)
    pu, pm = ParametrosUmbral(), ParametrosManiobra()
    con = conectar()
    tramos = leer_tramos(con)
    print(f"Parámetros: {parametros_como_texto(pu, pm)}")
    resultados = []
    for p in lista:
        try:
            r = procesar(p, tramos, pu, pm)
        except Exception as e:  # un recorrido malo no detiene los demás
            print(f"  {p.name}: OMITIDO ({e})")
            continue
        resultados.append(r)
        r["pre"].drop(columns="geometry", errors="ignore").to_csv(
            salida / f"preetiquetas_{r['nombre']}.csv", index=False, encoding="utf-8")
        n_ev = 0 if args.sin_base else guardar_eventos(con, r, args.origen)
        conf = (r["pre"]["etiqueta_copiloto"] != "").sum() if len(r["pre"]) else 0
        n_et = 0 if r["etiquetas"] is None else len(r["etiquetas"])
        print(f"  {r['nombre']}: fs {r['fs']:.0f} Hz · {r['fijaciones_en_tramo']}/{r['n_fijaciones']} fijaciones "
              f"asignadas · {len(r['revisados'])} tramos revisados · {len(r['pre'])} candidatos del detector "
              f"({conf} coinciden con etiquetas del copiloto, de {n_et}) · {len(r['maniobras'])} maniobras · "
              f"{n_ev} eventos a la base")
    tr = tramos_revisados(resultados, args.usar_preetiquetas)
    tr.to_csv(salida / "tramos_revisados.csv", index=False, encoding="utf-8")
    print(f"tramos_revisados.csv: {len(tr)} tramos ({int(tr['tiene_hueco'].sum()) if len(tr) else 0} con hueco) "
          f"→ {salida / 'tramos_revisados.csv'}")


if __name__ == "__main__":
    main()
