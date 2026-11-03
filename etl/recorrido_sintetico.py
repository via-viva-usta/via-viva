"""Genera recorridos SINTÉTICOS en formato de export de phyphox, sobre calles reales de Tunja.

Sirve para PROBAR etl/recorridos.py (map-matching, detector, tramos revisados) sin datos reales. Nada de lo que
sale de aquí es un resultado: los huecos se ponen al azar. Todo queda marcado con el prefijo SINTETICO_.

Cada recorrido:
  * camino más corto entre dos intersecciones de la zona urbana (grafo de la tabla tramos), 2 a 4 km;
  * velocidad 12-30 km/h (más lenta en las curvas), GPS a 1 Hz con ruido de ~3 m;
  * acelerómetro a 400 Hz con vibración de la vía, y huecos/resaltos en tramos elegidos al azar;
  * giroscopio con el giro real del camino (cambio de rumbo) → giros izquierda/derecha;
  * celular inclinado (orientación libre) y _etiquetas.csv del "copiloto" con error de ±0,3 s.
Además escribe SINTETICO_verdad.csv: qué tramos tienen hueco de verdad, para medir si el procesamiento los recupera.

Uso (desde via-viva/):
  etl\\.venv\\Scripts\\python -m etl.recorrido_sintetico --n 3
  etl\\.venv\\Scripts\\python -m etl.recorridos --carpeta data/raw/phyphox_sintetico --salida data/campo/sintetico --sin-base
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from shapely import wkt

from etl.config import DATA, TUNJA_LAT, TUNJA_LON
from etl.db import conectar

G0 = 9.80665
CARPETA = DATA / "raw" / "phyphox_sintetico"


def grafo(con) -> tuple[nx.Graph, dict, dict]:
    t = pd.read_sql("SELECT id_tramo, osm_u, osm_v, longitud_m, geometria_wkt, lat_centro, lon_centro FROM tramos", con)
    n = pd.read_sql("SELECT osm_id, lat, lon FROM nodos", con).set_index("osm_id")
    G = nx.Graph()
    for f in t.itertuples():
        # solo la zona urbana (≤ 3 km del centro): ahí se harían los recorridos
        if np.hypot((f.lat_centro - TUNJA_LAT) * 111, (f.lon_centro - TUNJA_LON) * 110) > 3:
            continue
        G.add_edge(f.osm_u, f.osm_v, peso=f.longitud_m, id_tramo=f.id_tramo, geom=f.geometria_wkt)
    return G, n.to_dict("index"), t.set_index("id_tramo")["longitud_m"].to_dict()


def camino(G, nodos, rng) -> list[tuple[int, list[tuple[float, float]]]]:
    """Lista de (id_tramo, puntos lat/lon en el sentido del recorrido)."""
    lista = list(G.nodes)
    for _ in range(200):
        a, b = rng.choice(lista, 2, replace=False)
        try:
            ruta = nx.shortest_path(G, a, b, weight="peso")
        except nx.NetworkXNoPath:
            continue
        largo = sum(G[u][v]["peso"] for u, v in zip(ruta, ruta[1:]))
        if 2000 <= largo <= 4000:
            break
    tramos = []
    for u, v in zip(ruta, ruta[1:]):
        datos = G[u][v]
        coords = [(y, x) for x, y in wkt.loads(datos["geom"]).coords]
        # orientar la geometría en el sentido u → v
        if np.hypot(coords[0][0] - nodos[u]["lat"], coords[0][1] - nodos[u]["lon"]) > \
           np.hypot(coords[-1][0] - nodos[u]["lat"], coords[-1][1] - nodos[u]["lon"]):
            coords = coords[::-1]
        tramos.append((datos["id_tramo"], coords))
    return tramos


def a_metros(lat, lon):
    return (np.asarray(lon) - TUNJA_LON) * 111320 * np.cos(np.radians(TUNJA_LAT)), (np.asarray(lat) - TUNJA_LAT) * 110574


def generar(nombre: str, G, nodos, rng, fs_acc=400.0) -> pd.DataFrame:
    ruta = camino(G, nodos, rng)
    # polilínea continua con el tramo de cada punto
    lat, lon, idt = [], [], []
    for id_tramo, coords in ruta:
        for la, lo in coords[(1 if lat else 0):]:
            lat.append(la); lon.append(lo); idt.append(id_tramo)
    x, y = a_metros(lat, lon)
    seg = np.hypot(np.diff(x), np.diff(y))
    s = np.r_[0, np.cumsum(seg)]                        # distancia acumulada
    rumbo = np.unwrap(np.arctan2(np.diff(y), np.diff(x)))
    # velocidad: 30 km/h en recta, más lenta donde el rumbo cambia mucho
    curv = np.abs(np.gradient(rumbo)) / np.maximum(seg, 1)
    v_obj = np.clip(30 / 3.6 - 60 * curv, 12 / 3.6, 30 / 3.6)
    dt = 1 / fs_acc
    t, pos, v = [0.0], [0.0], [3.0]
    while pos[-1] < s[-1]:
        k = min(np.searchsorted(s, pos[-1]), len(v_obj) - 1)
        nv = v[-1] + np.clip(v_obj[k] - v[-1], -1.5 * dt, 1.0 * dt)
        v.append(nv); pos.append(pos[-1] + nv * dt); t.append(t[-1] + dt)
    t, pos, v = np.array(t), np.array(pos), np.array(v)
    xs, ys = np.interp(pos, s, x), np.interp(pos, s, y)
    rumbo_t = np.unwrap(np.arctan2(np.gradient(ys), np.gradient(xs)))
    yaw = np.gradient(rumbo_t, t)                       # rad/s, positivo = antihorario = izquierda
    yaw = np.convolve(yaw, np.ones(int(fs_acc / 2)) / int(fs_acc / 2), mode="same")

    # vibración vertical + eventos en tramos al azar (25 % huecos, 10 % resaltos)
    vert = np.convolve(rng.normal(0, 1.0, t.size), np.ones(8) / 8, mode="same") * (0.6 + 0.04 * v)
    tramos_ruta = list(dict.fromkeys(idt))
    etiquetas, verdad = [], []
    for id_tramo in tramos_ruta:
        r = rng.random()
        clase = "hueco" if r < 0.25 else "resalto" if r < 0.35 else None
        if clase is None:
            continue
        idx = [i for i, x_ in enumerate(idt) if x_ == id_tramo]
        # los vértices de un tramo son su final y sus puntos intermedios; su inicio es el último vértice
        # del tramo anterior (por eso idx[0] - 1)
        s_mid = (s[max(idx[0] - 1, 0)] + s[idx[-1]]) / 2
        te = float(np.interp(s_mid, pos, t))
        tau = t - te
        m = (tau >= 0) & (tau < 1.2)
        if clase == "hueco":
            vert[m] += -7 * np.exp(-tau[m] / 0.08) * np.cos(2 * np.pi * 11 * tau[m])
        else:
            vert[m] += 4.5 * np.sin(2 * np.pi * 1.2 * tau[m]) * np.exp(-tau[m] / 0.4)
        etiquetas.append((round(te + rng.normal(0, 0.3), 2), clase))
        verdad.append({"recorrido": nombre, "id_tramo": id_tramo, "clase": clase, "t_s": te})

    # celular inclinado: rotar (vertical, adelante, yaw) a los ejes del teléfono
    ang = np.radians(rng.uniform(15, 35))
    adelante = np.gradient(v, t)
    ax_ = adelante
    ay_ = (G0 + vert) * np.sin(ang)
    az_ = (G0 + vert) * np.cos(ang)
    gx_ = np.zeros_like(t)
    gy_ = yaw * np.sin(ang) + rng.normal(0, 0.01, t.size)
    gz_ = yaw * np.cos(ang) + rng.normal(0, 0.01, t.size)

    d = CARPETA / f"SINTETICO_{nombre}"
    (d / "meta").mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"Time (s)": t, "Acceleration x (m/s^2)": ax_, "Acceleration y (m/s^2)": ay_,
                  "Acceleration z (m/s^2)": az_}).to_csv(d / "Accelerometer.csv", index=False)
    pd.DataFrame({"Time (s)": t, "Gyroscope x (rad/s)": gx_, "Gyroscope y (rad/s)": gy_,
                  "Gyroscope z (rad/s)": gz_}).to_csv(d / "Gyroscope.csv", index=False)
    tg = np.arange(0, t[-1], 1.0)
    xg, yg = np.interp(np.interp(tg, t, pos), s, x), np.interp(np.interp(tg, t, pos), s, y)
    xg, yg = xg + rng.normal(0, 3, tg.size), yg + rng.normal(0, 3, tg.size)
    pd.DataFrame({"Time (s)": tg, "Latitude (°)": TUNJA_LAT + yg / 110574,
                  "Longitude (°)": TUNJA_LON + xg / (111320 * np.cos(np.radians(TUNJA_LAT))),
                  "Height (m)": 2800.0, "Velocity (m/s)": np.interp(tg, t, v), "Direction (°)": 0.0,
                  "Horizontal Accuracy (m)": 4.0, "Vertical Accuracy (m)": 8.0}).to_csv(d / "Location.csv", index=False)
    pd.DataFrame({"event": ["START"], "experiment time": [0.0], "system time": [1793520000.0],
                  "system time text": ["2026-11-01 08:00:00.000 UTC-05:00"]}).to_csv(d / "meta" / "time.csv", index=False)
    pd.DataFrame(etiquetas, columns=["t_s", "clase"]).to_csv(CARPETA / f"SINTETICO_{nombre}_etiquetas.csv", index=False)
    print(f"  SINTETICO_{nombre}: {s[-1] / 1000:.1f} km, {t[-1]:.0f} s, {len(tramos_ruta)} tramos, "
          f"{sum(1 for v_ in verdad if v_['clase'] == 'hueco')} huecos y "
          f"{sum(1 for v_ in verdad if v_['clase'] == 'resalto')} resaltos puestos")
    return pd.DataFrame(verdad).assign(tramos_en_ruta=len(tramos_ruta)), tramos_ruta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--semilla", type=int, default=7)
    args = ap.parse_args()
    if CARPETA.exists():
        shutil.rmtree(CARPETA)
    CARPETA.mkdir(parents=True)
    rng = np.random.default_rng(args.semilla)
    G, nodos, _ = grafo(conectar())
    print(f"Generando {args.n} recorridos SINTÉTICOS en {CARPETA}")
    verdades, rutas = [], []
    for i in range(args.n):
        v, tr = generar(f"ruta{i + 1}", G, nodos, rng)
        verdades.append(v)
        rutas.append(pd.DataFrame({"recorrido": f"ruta{i + 1}", "id_tramo": tr}))
    pd.concat(verdades).to_csv(CARPETA / "_SINTETICO_verdad.csv", index=False)
    pd.concat(rutas).to_csv(CARPETA / "_SINTETICO_tramos_en_ruta.csv", index=False)


if __name__ == "__main__":
    main()
