"""Pruebas del detector por umbrales (lo usa etl/recorridos.py) y de la validación espacial del modelo de riesgo."""
import numpy as np
import pandas as pd
import pytest

from analysis.detector_umbral import ParametrosUmbral, detectar_umbral


def _senal(fs=100, dur=20, golpes=(8.0, 14.0)):
    rng = np.random.default_rng(1)
    a = rng.normal(0, 0.02, int(fs * dur))
    for g in golpes:
        i = int(g * fs)
        a[i:i + 3] += [0.8, -0.9, 0.5]
    return a


def test_detecta_golpes_con_velocidad():
    fs = 100
    ev = detectar_umbral(_senal(fs), np.full(20 * fs, 20.0), fs, ParametrosUmbral())
    assert sorted(round(i / fs) for i in ev["indice"]) == [8, 14]


def test_no_dispara_con_el_carro_detenido():
    """etl/recorridos.py pone velocidad 0 en las paradas del cronómetro: no debe haber eventos ahí."""
    fs = 100
    vel = np.full(20 * fs, 20.0)
    vel[int(12 * fs):int(16 * fs)] = 0.0                    # parada entre 12 s y 16 s
    ev = detectar_umbral(_senal(fs), vel, fs, ParametrosUmbral())
    assert sorted(round(i / fs) for i in ev["indice"]) == [8]


def test_riesgo_validacion_espacial_sintetica():
    rm = pytest.importorskip("risk_model.modelo")
    rng = np.random.default_rng(0)
    n = 120
    v = pd.DataFrame({c: rng.normal(size=n) for c in rm.NUMERICAS})
    for c in rm.CATEGORICAS:
        v[c] = rng.choice(["a", "b", "c"], n)
    v["barrio"] = rng.choice([f"B{i}" for i in range(6)], n)
    v["etiqueta"] = (v[rm.NUMERICAS[0]] + rng.normal(0, 0.5, n) > 0).astype(float)
    r = rm.validar(v, "barrio")
    assert r["n"] == n and r["grupos"] == 6
    assert 0.5 < r["logistica"]["auc_espacial"] <= 1.0      # la etiqueta depende de una variable: debe aprender algo
    with pytest.raises(SystemExit):
        rm.validar(v.head(10), "barrio")                     # menos de 30 etiquetados: se niega a entrenar
