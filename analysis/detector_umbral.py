"""Detector por umbrales y maniobras: la MISMA regla que el firmware (src/detector_umbral.h y src/maniobras.h).

Se usa para:
  * pre-etiquetar recorridos (etl/recorridos.py): marca candidatos que el equipo confirma o corrige;
  * ser la línea base contra la que se compara el clasificador (analysis/entrenar_detector.py).

Regla del detector (muestra a muestra; mismos parámetros por defecto que firmware/nodo-sensores/include/config.h):
  1. a[n]   = aceleración vertical dinámica (g)
  2. p2p[n] = max(a) - min(a) en las últimas round(ventana_p2p_s * fs) muestras
  3. ms2[n] = ms2[n-1] + alfa * (a[n]^2 - ms2[n-1]),  alfa = 1 / (tau_base_s * fs);  rms = sqrt(ms2)
  4. evento si: n >= tau_base_s * fs (línea base ya estable)
                y velocidad > v_min_kmh
                y p2p[n] > k_rel * rms[n-1]  y  p2p[n] > p2p_min_g
                y pasaron refractario_s desde el último evento

Maniobras (con el giroscopio):
  giro izquierda / derecha: velocidad angular alrededor de la vertical, filtrada (tau 0,25 s),
      mayor que +giro_min_dps / menor que -giro_min_dps durante dur_giro_s, con velocidad > v_min.
      Positivo = antihorario visto desde arriba = izquierda.
  frenada brusca: caída de la velocidad GPS más rápida que frenada_gps_ms2.
En el celular la orientación es libre: la vertical se estima con la gravedad (pasa-bajos del acelerómetro con g)
y el giro se proyecta sobre ella.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass
class ParametrosUmbral:
    v_min_kmh: float = 5.0
    k_rel: float = 6.0
    p2p_min_g: float = 0.30
    tau_base_s: float = 2.0
    ventana_p2p_s: float = 0.05
    refractario_s: float = 1.0


@dataclass
class ParametrosManiobra:
    giro_min_dps: float = 15.0
    dur_giro_s: float = 1.0
    frenada_gps_ms2: float = 2.5
    v_min_kmh: float = 5.0
    tau_filtro_s: float = 0.25


def detectar_umbral(a_g: np.ndarray, vel_kmh: np.ndarray, fs: float,
                    p: ParametrosUmbral | None = None) -> pd.DataFrame:
    """Devuelve una fila por evento: indice, p2p_g, rms_base_g, razon. a_g en g; vel_kmh por muestra."""
    p = p or ParametrosUmbral()
    n_p2p = int(np.clip(round(p.ventana_p2p_s * fs), 2, 64))
    alfa = 1.0 / (p.tau_base_s * fs)
    calentamiento = int(p.tau_base_s * fs)
    refractario = int(p.refractario_s * fs)
    ms2 = 0.0
    ultimo = None
    filas = []
    for n, (a, v) in enumerate(zip(a_g, vel_kmh)):
        ini = max(0, n - n_p2p + 1)
        seg = a_g[ini:n + 1]
        p2p = float(seg.max() - seg.min())
        rms_ant = float(np.sqrt(ms2))
        if (n >= calentamiento and v > p.v_min_kmh and p2p > p.k_rel * rms_ant and p2p > p.p2p_min_g
                and (ultimo is None or n - ultimo >= refractario)):
            ultimo = n
            filas.append({"indice": n, "p2p_g": p2p, "rms_base_g": rms_ant,
                          "razon": p2p / rms_ant if rms_ant > 1e-6 else np.inf})
        ms2 += alfa * (float(a) * float(a) - ms2)
    return pd.DataFrame(filas, columns=["indice", "p2p_g", "rms_base_g", "razon"])


def giro_vertical(acc: np.ndarray, giro: np.ndarray, fs: float) -> np.ndarray:
    """Velocidad angular (°/s) alrededor de la vertical, para un celular en cualquier orientación.

    acc: aceleración CON g (m/s² o g, N×3); giro: velocidad angular (rad/s, N×3) en los mismos ejes.
    """
    from scipy import signal
    sos = signal.butter(2, 0.3, fs=fs, output="sos")
    arriba = signal.sosfiltfilt(sos, acc, axis=0)
    arriba /= np.linalg.norm(arriba, axis=1, keepdims=True)
    return np.degrees(np.einsum("ij,ij->i", giro, arriba))


def detectar_maniobras(giro_dps: np.ndarray, vel_kmh: np.ndarray, fs: float,
                       decel_ms2: np.ndarray | None = None, p: ParametrosManiobra | None = None) -> pd.DataFrame:
    """Intervalos de maniobra: inicio, fin (índices) y tipo (giro_izquierda, giro_derecha, frenada_brusca)."""
    p = p or ParametrosManiobra()
    alfa = 1.0 / (p.tau_filtro_s * fs + 1.0)
    decel = np.zeros_like(giro_dps) if decel_ms2 is None else decel_ms2
    filtrado = 0.0
    en_curso, desde = None, 0
    filas = []

    def cerrar(fin):
        dur_min = 0 if en_curso == "frenada_brusca" else p.dur_giro_s * fs
        if en_curso and fin - desde >= dur_min:
            filas.append({"inicio": desde, "fin": fin, "tipo": en_curso})

    for n, (g, v, d) in enumerate(zip(giro_dps, vel_kmh, decel)):
        filtrado += alfa * (g - filtrado)
        mov = v > p.v_min_kmh
        tipo = ("giro_izquierda" if mov and filtrado > p.giro_min_dps else
                "giro_derecha" if mov and filtrado < -p.giro_min_dps else
                "frenada_brusca" if d > p.frenada_gps_ms2 else None)
        if tipo != en_curso:
            cerrar(n)
            en_curso, desde = tipo, n
    cerrar(len(giro_dps))
    return pd.DataFrame(filas, columns=["inicio", "fin", "tipo"])


def parametros_como_texto(pu: ParametrosUmbral | None = None, pm: ParametrosManiobra | None = None) -> str:
    """Para dejar escrito en cada salida con qué parámetros se pre-etiquetó."""
    return f"umbral={asdict(pu or ParametrosUmbral())}; maniobra={asdict(pm or ParametrosManiobra())}"
