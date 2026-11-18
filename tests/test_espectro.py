"""analysis/espectro.py con un export SINTÉTICO de phyphox: la frecuencia del 95 % y la fs recomendada se conocen."""
import csv

import numpy as np

from analysis import espectro


def _export_sintetico(ruta, fs=100.0, dur=40.0, f_vib=12.0, semilla=0):
    """CSV con el formato de phyphox ("Acceleration with g"): gravedad en z y una vibración vertical de f_vib Hz."""
    rng = np.random.default_rng(semilla)
    t = np.arange(0, dur, 1 / fs)
    az = 9.81 + 2.0 * np.sin(2 * np.pi * f_vib * t) + 0.05 * rng.standard_normal(t.size)
    ax = 0.05 * rng.standard_normal(t.size)
    ay = 0.05 * rng.standard_normal(t.size)
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Time (s)", "Acceleration x (m/s^2)", "Acceleration y (m/s^2)", "Acceleration z (m/s^2)"])
        w.writerows(zip(t, ax, ay, az))
    return ruta


def test_frecuencia_de_energia_y_fs_recomendada(tmp_path):
    filas, _ = espectro.analizar(_export_sintetico(tmp_path / "sintetico.csv"))
    v = next(f for f in filas if f["senal"] == "vertical")
    assert abs(v["fs_nativa_hz"] - 100.0) < 0.5
    assert 11.0 <= v["f_energia_hz"] <= 13.0           # la vibración de 12 Hz concentra la energía
    assert abs(v["fs_minima_hz"] - 2 * v["f_energia_hz"]) < 0.02
    assert abs(v["fs_recomendada_hz"] - 2.5 * v["f_energia_hz"]) < 0.02
    assert v["aviso"] == ""


def test_avisa_si_la_energia_esta_cerca_de_nyquist(tmp_path):
    filas, _ = espectro.analizar(_export_sintetico(tmp_path / "alto.csv", fs=50.0, f_vib=23.0))
    assert next(f for f in filas if f["senal"] == "vertical")["aviso"]


def test_cli_escribe_tabla_y_markdown(tmp_path, capsys):
    ruta = _export_sintetico(tmp_path / "rec.csv")
    assert espectro.main([str(ruta), "--salida", str(tmp_path / "out")]) == 0
    assert (tmp_path / "out" / "rec_espectro.csv").exists()
    md = (tmp_path / "out" / "rec_espectro.md").read_text(encoding="utf-8")
    assert "Recomendación (eje vertical)" in md
    assert "Eje vertical" in capsys.readouterr().out
