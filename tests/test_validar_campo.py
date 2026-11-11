"""Pruebas del validador de campo con un export de phyphox y fotos fabricados (SINTÉTICOS) en una carpeta temporal."""
from datetime import datetime

import numpy as np
import pandas as pd

from herramientas.validar_campo import Informe, revisar_fotos, revisar_phyphox


def _phyphox(carpeta, fs=100, dur=240, quieto_s=65, columnas=None):
    t = np.arange(0, dur, 1 / fs)
    rng = np.random.default_rng(0)
    vib = np.where((t > quieto_s) & (t < dur - quieto_s), 0.25, 0.005) * 9.81
    az = 9.81 + rng.normal(0, 1, t.size) * vib
    nombres = columnas or ["Time (s)", "Acceleration x (m/s^2)", "Acceleration y (m/s^2)", "Acceleration z (m/s^2)"]
    carpeta.mkdir()
    pd.DataFrame({nombres[0]: t, nombres[1]: rng.normal(0, 0.05, t.size), nombres[2]: rng.normal(0, 0.05, t.size),
                  nombres[3]: az}).to_csv(carpeta / "Accelerometer.csv", index=False)
    tg = np.arange(0, dur, 1.0)
    pd.DataFrame({"Time (s)": tg, "Latitude (°)": 5.53 + tg * 1e-5, "Longitude (°)": -73.36 + 0 * tg,
                  "Velocity (m/s)": np.full(tg.size, 5.0)}).to_csv(carpeta / "Location.csv", index=False)
    return carpeta


def test_phyphox_bien(tmp_path):
    inf = Informe()
    revisar_phyphox(_phyphox(tmp_path / "r1"), inf)
    texto = "\n".join(inf.lineas)
    assert "tasa del acelerómetro 100 Hz" in texto
    assert "1 min quieto al inicio" in texto and "1 min quieto al final" in texto
    assert "CORREGIR: sin giroscopio" in texto            # el export de prueba no lo trae
    assert "sin etiquetas del copiloto" in texto


def test_phyphox_columnas_de_ios(tmp_path):
    """El export de phyphox en iOS (7-nov) trae 'X (m/s^2)' sin la palabra 'Acceleration'."""
    inf = Informe()
    revisar_phyphox(_phyphox(tmp_path / "ios", columnas=["Time (s)", "X (m/s^2)", "Y (m/s^2)", "Z (m/s^2)"]), inf)
    assert any("BIEN: tasa del acelerómetro 100 Hz" in l for l in inf.lineas)


def test_phyphox_columnas_desconocidas(tmp_path):
    inf = Informe()
    revisar_phyphox(_phyphox(tmp_path / "r2", columnas=["t", "x", "y", "z"]), inf)
    assert any("Columnas que vi" in l and "'x'" not in l and "x, y, z" in l for l in inf.lineas)


def test_fotos_sin_gps_y_pequenas(tmp_path):
    from PIL import Image

    from dataset.sintetico import guardar_con_exif
    c = tmp_path / "2026-11-06_juandiego"
    c.mkdir()
    guardar_con_exif(np.full((480, 640, 3), 110, np.uint8), c / "a.jpg", datetime(2026, 11, 6, 10), 5.53, -73.36)
    Image.new("RGB", (640, 480), (90, 90, 90)).save(c / "b.jpg")                       # sin EXIF
    inf = Informe()
    df = revisar_fotos(tmp_path, inf)
    texto = "\n".join(inf.lineas)
    assert len(df) == 2
    assert "1 de 2 fotos sin GPS" in texto and "1 de 2 fotos sin fecha y hora" in texto
    assert "fotos de menos de 3 MP" in texto
    assert "sin la tarjeta" in texto
