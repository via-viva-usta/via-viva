"""Lectura y preparación de la señal de una sesión (carpeta de la captura o export de phyphox, .zip o carpeta).

- Remuestreo a una rejilla uniforme (100 Hz por defecto) con interpolación lineal; los cortes > 0,1 s se marcan.
- **Eje vertical:** la gravedad se estima con un filtro pasa-bajos (τ = 0,5 s) sobre cada eje; la aceleración vertical
  es la proyección sobre esa dirección menos 1 g. Así no importa cómo quedó montado el celular o la caja.
- Velocidad (km/h) y posición del GPS interpoladas a cada muestra.
Lo usan `viaviva/detector.py` (detector calibrable) y `viaviva/ventanas.py` (dataset).
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from viaviva.fuentes import _leer_tabla

G = 9.81


@dataclass
class Senal:
    nombre: str
    fs: float
    t: np.ndarray            # s desde el inicio de la grabación
    a_v: np.ndarray          # aceleración vertical sin gravedad (g)
    a_h: np.ndarray          # módulo de la aceleración horizontal (g)
    vel_kmh: np.ndarray      # velocidad del GPS interpolada (NaN sin GPS)
    lat: np.ndarray
    lon: np.ndarray
    hueco_datos: np.ndarray  # True donde la muestra se interpoló sobre un corte > 0,1 s
    etiquetas: list[tuple[float, str]] = field(default_factory=list)
    inicio_epoch: float | None = None


def leer_etiquetas(ruta: Path) -> list[tuple[float, str]]:
    """Etiquetas vigentes: `<carpeta>_etiquetas.csv` (t_s, clase), como las deja la captura y etl.recorridos."""
    ruta = Path(ruta)
    for cand in (ruta.parent / f"{ruta.stem if ruta.is_file() else ruta.name}_etiquetas.csv",
                 ruta / "etiquetas_vigentes.csv" if ruta.is_dir() else None):
        if cand and cand.exists():
            with open(cand, encoding="utf-8-sig") as f:
                return sorted((float(r["t_s"]), r["clase"].strip()) for r in csv.DictReader(f) if r.get("t_s"))
    return []


def _ema(x: np.ndarray, alfa: float) -> np.ndarray:
    y = np.empty_like(x)
    acc = x[0]
    for i, v in enumerate(x):
        acc += alfa * (v - acc)
        y[i] = acc
    return y


def preparar(t_crudo, ax, ay, az, gps: list[list[float]], fs: float = 100.0, nombre: str = "",
             tau_gravedad_s: float = 0.5) -> Senal:
    t_crudo = np.asarray(t_crudo, float)
    orden = np.argsort(t_crudo)
    t_crudo = t_crudo[orden]
    a = np.column_stack([np.asarray(ax, float)[orden], np.asarray(ay, float)[orden], np.asarray(az, float)[orden]])
    t0 = t_crudo[0]
    t = np.arange(t0, t_crudo[-1], 1.0 / fs)
    a_u = np.column_stack([np.interp(t, t_crudo, a[:, k]) for k in range(3)]) / G
    dt = np.diff(t_crudo)
    hueco = np.zeros(len(t), bool)
    for i in np.flatnonzero(dt > 0.1):
        hueco |= (t > t_crudo[i]) & (t < t_crudo[i + 1])
    alfa = 1.0 / (tau_gravedad_s * fs)
    grav = np.column_stack([_ema(a_u[:, k], alfa) for k in range(3)])
    norma = np.linalg.norm(grav, axis=1, keepdims=True)
    norma[norma == 0] = 1.0
    g_hat = grav / norma
    a_vert_total = np.sum(a_u * g_hat, axis=1)
    a_v = a_vert_total - norma[:, 0]
    a_h = np.linalg.norm(a_u - a_vert_total[:, None] * g_hat, axis=1)
    if gps:
        g = np.array([f[:5] + [math.nan] * (5 - len(f[:5])) for f in gps], float)
        g = g[np.argsort(g[:, 0])]
        def interp(col):
            ok = ~np.isnan(g[:, col]) & ((g[:, 4] >= 0) if col == 4 else True)
            if ok.sum() < 2:
                return np.full(len(t), np.nan)
            y = np.interp(t, g[ok, 0], g[ok, col])
            y[(t < g[ok, 0][0] - 2) | (t > g[ok, 0][-1] + 2)] = np.nan
            return y
        vel = interp(4) * 3.6
        lat, lon = interp(1), interp(2)
    else:
        vel = lat = lon = np.full(len(t), np.nan)
    return Senal(nombre, fs, t - t0, a_v, a_h, vel, lat, lon, hueco)


def cargar(ruta: Path, fs: float = 100.0) -> Senal:
    ruta = Path(ruta)
    acc = [f for f in _leer_tabla(ruta, "Accelerometer.csv") if len(f) >= 4 and not math.isnan(f[0])]
    if len(acc) < fs:
        raise ValueError(f"{ruta}: muy pocas muestras del acelerómetro ({len(acc)})")
    gps = _leer_tabla(ruta, "Location.csv")
    s = preparar([f[0] for f in acc], [f[1] for f in acc], [f[2] for f in acc], [f[3] for f in acc], gps, fs,
                 ruta.stem if ruta.is_file() else ruta.name)
    t0 = acc[0][0]                       # las etiquetas usan el mismo tiempo que Accelerometer.csv
    s.etiquetas = [(t - t0, c) for t, c in leer_etiquetas(ruta)]
    meta = _leer_tabla(ruta, "time.csv")
    if meta and len(meta[0]) > 2 and not math.isnan(meta[0][2]):
        s.inicio_epoch = meta[0][2] + t0
    return s


def sesiones_en(rutas: list[Path]) -> list[Path]:
    """Expande carpetas: cada sesion_* o export .zip dentro cuenta como una sesión."""
    salida = []
    for r in map(Path, rutas):
        if r.is_dir() and not (r / "Accelerometer.csv").exists():
            salida += sorted([p for p in r.iterdir() if (p.is_dir() and (p / "Accelerometer.csv").exists())
                              or p.suffix.lower() == ".zip"])
        else:
            salida.append(r)
    return salida
