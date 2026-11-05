"""Pruebas del dataset de fotos: utilidades, EXIF de la ingesta y planilla de campo. Sin datos reales ni internet."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from dataset import planilla
from dataset.comun import COLUMNAS, autor_de_carpeta, momento_dia, sitios


@pytest.mark.parametrize("hora,momento", [(3, "madrugada"), (7, "manana"), (12, "mediodia"), (15, "tarde"),
                                          (19, "noche")])
def test_momento_dia(hora, momento):
    assert momento_dia(hora) == momento


def test_autor_de_carpeta():
    assert autor_de_carpeta("2026-11-06_JuanDiego") == "juandiego"
    assert autor_de_carpeta("fotos sueltas") == "fotos sueltas"


def test_superficie_en_el_esquema():
    assert COLUMNAS.index("superficie") == COLUMNAS.index("tipo_via") + 1


def _meta(filas):
    base = {c: "" for c in COLUMNAS}
    return pd.DataFrame([{**base, **f} for f in filas])


def test_sitios_por_gps_y_por_hora():
    m = _meta([{"lat": "5.53000", "lon": "-73.36000", "autor": "a", "fecha": "2026-11-06", "hora": "10:00:00"},
               {"lat": "5.53005", "lon": "-73.36005", "autor": "a", "fecha": "2026-11-06", "hora": "10:00:30"},  # ~8 m
               {"lat": "5.54000", "lon": "-73.36000", "autor": "a", "fecha": "2026-11-06", "hora": "10:20:00"},
               {"autor": "b", "fecha": "2026-11-06", "hora": "11:00:00"},                                        # sin GPS
               {"autor": "b", "fecha": "2026-11-06", "hora": "11:05:00"}])
    s = sitios(m)
    assert s[0] == s[1] != s[2]
    assert s[3] == s[4] != s[0]


def test_exif_con_gps_y_zona(tmp_path):
    from PIL import Image
    from dataset.ingesta import leer_exif
    from dataset.sintetico import guardar_con_exif
    ruta = tmp_path / "foto.jpg"
    guardar_con_exif(np.full((48, 64, 3), 120, np.uint8), ruta, datetime(2026, 11, 6, 15, 30), 5.5353, -73.3678)
    ex = leer_exif(Image.open(ruta))
    assert ex["t"] == datetime(2026, 11, 6, 15, 30, tzinfo=timezone(timedelta(hours=-5)))
    assert ex["lat"] == pytest.approx(5.5353, abs=1e-5) and ex["lon"] == pytest.approx(-73.3678, abs=1e-5)


def test_planilla_lee_y_une(tmp_path):
    pd.DataFrame([
        {"N.º": 1, "Fecha": "6/11/2026", "Hora": "3:30 p. m.", "Clase": "Bache", "Severidad": "Alta",
         "Tipo de vía": "Adoquín", "¿Mojado?": "Sí", "Luz": "Nublado", "Clima": "llovizna", "Barrio/calle": "Centro",
         "Fotógrafo": "Juan Diego", "N.º fotos": 4, "Notas": ""},
        {"N.º": 2, "Fecha": "6/11/2026", "Hora": "18:00", "Clase": "Cebra", "Severidad": "", "Tipo de vía": "asfalto",
         "¿Mojado?": "no", "Luz": "noche", "Clima": "", "Barrio/calle": "", "Fotógrafo": "", "N.º fotos": 2, "Notas": ""},
    ]).to_csv(tmp_path / "planilla.csv", index=False, encoding="utf-8-sig")
    t, avisos = planilla.leer(tmp_path)
    assert not avisos
    assert list(t["clase_n"]) == ["hueco", "paso_peatonal"]
    assert list(t["superficie_n"]) == ["adoquin", "asfalto"]
    assert t["t"].iloc[0] == pd.Timestamp("2026-11-06 15:30")
    m = _meta([{"id": "a", "autor": "juandiego", "fecha": "2026-11-06", "hora": "15:33:00", "lat": "5.53", "lon": "-73.36"},
               {"id": "b", "autor": "juandiego", "fecha": "2026-11-06", "hora": "15:40:00", "lat": "5.53", "lon": "-73.36"},
               {"id": "c", "autor": "juandiego", "fecha": "2026-11-06", "hora": "12:00:00", "lat": "5.60", "lon": "-73.30",
                "clase": "tapa"}])
    m2, est = planilla.unir(m, t, sitios(m))
    assert est["filas_unidas"] == 1
    assert list(m2["clase"]) == ["hueco", "hueco", "tapa"]          # b entra por ser del mismo sitio; c no se pisa
    assert m2.loc[0, "superficie"] == "adoquin" and m2.loc[0, "severidad"] == "alta"
    assert "clima=llovizna" in m2.loc[1, "notas"]


def test_planilla_avisa_columnas(tmp_path):
    pd.DataFrame([{"Dia": 1}]).to_csv(tmp_path / "mala.csv", index=False)
    t, avisos = planilla.leer(tmp_path)
    assert t.empty and "no encontré las columnas" in avisos[0]
