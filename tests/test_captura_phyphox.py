"""Pruebas de herramientas/captura_phyphox_remoto.py con un export de iOS fabricado (SINTÉTICO) y el simulador."""
import csv
import threading
import time

import numpy as np
import pandas as pd
import pytest

from analysis.detector_umbral import ParametrosUmbral, detectar_umbral
from herramientas import captura_phyphox_remoto as cp
from herramientas.validar_campo import Informe, revisar_phyphox


def _export_ios(carpeta, dur=20.0, fs=100):
    carpeta.mkdir()
    t = np.arange(0, dur, 1 / fs)
    rng = np.random.default_rng(0)
    for g, cols in [("acc", [rng.normal(0, .1, t.size), rng.normal(0, .1, t.size), 9.81 + rng.normal(0, .3, t.size)]),
                    ("giro", [rng.normal(0, .01, t.size)] * 3)]:
        d = cp.GRUPOS[g]
        pd.DataFrame(dict(zip(d["encabezado"], [t, *cols]))).to_csv(carpeta / d["archivo"], index=False)
    tg = np.arange(0, dur, 1.0)
    d = cp.GRUPOS["gps"]
    pd.DataFrame(dict(zip(d["encabezado"], [tg, 5.53 + tg * 1e-5, -73.36 + 0 * tg, 2700 + 0 * tg, 5 + 0 * tg,
                                            90 + 0 * tg, 4 + 0 * tg, 3 + 0 * tg]))).to_csv(carpeta / d["archivo"], index=False)
    return carpeta


def _capturar(origen, destino, velocidad=40.0, pausa_en=None):
    sim = cp.SimuladorPhyphox(origen, velocidad)
    cap = cp.Captura(destino)
    parar = threading.Event()
    hilo = threading.Thread(target=cp.bucle, args=(cp.Cliente(sim.url, timeout=0.5), cap, parar, False, True))
    hilo.start()
    if pausa_en is not None:
        time.sleep(pausa_en)
        sim.pausado = True            # corte de conexión
        time.sleep(1.5)
        sim.pausado = False
    hilo.join(30)
    cap.cerrar()
    sim.cerrar()
    return cap


def test_reproduccion_identica_al_export(tmp_path):
    origen = _export_ios(tmp_path / "export")
    cap = _capturar(origen, tmp_path / "salida" / "rec")
    for g in cp.GRUPOS.values():
        o, c = pd.read_csv(origen / g["archivo"]), pd.read_csv(cap.carpeta / g["archivo"])
        assert list(c.columns) == g["encabezado"]
        assert c.shape == o.shape and np.allclose(o.to_numpy(), c.to_numpy(), equal_nan=True)
    inf = Informe()
    revisar_phyphox(cap.carpeta, inf)                     # el validador acepta la captura sin cambios
    assert any("BIEN: tasa del acelerómetro 100 Hz" in l for l in inf.lineas)


def test_corte_de_conexion_sin_perder_datos(tmp_path):
    origen = _export_ios(tmp_path / "export", dur=40.0)
    cap = _capturar(origen, tmp_path / "salida" / "rec", velocidad=20.0, pausa_en=0.5)
    assert cap.reconexiones >= 1
    assert any("CONEXIÓN PERDIDA" in m for m in cap.mensajes)
    assert len(pd.read_csv(cap.carpeta / "Accelerometer.csv")) == len(pd.read_csv(origen / "Accelerometer.csv"))


def test_etiquetas_con_posicion_y_paradas(tmp_path):
    cap = cp.Captura(tmp_path / "rec")
    cap.lat, cap.lon, cap.vel_kmh, cap.ultimo_t_acc = 5.53, -73.36, 18.0, 42.0
    cap.etiquetar("hueco")
    cap.etiquetar("parada")
    cap.etiquetar("parada")
    cap.cerrar()
    detalle = list(csv.DictReader(open(tmp_path / "rec" / "etiquetas.csv", encoding="utf-8")))
    assert [d["clase"] for d in detalle] == ["hueco", "parada_inicio", "parada_fin"]
    assert detalle[0]["lat"] == "5.53" and detalle[0]["t_s"] == "42.0"
    corto = pd.read_csv(tmp_path / "rec_etiquetas.csv")       # el que lee etl/recorridos.py
    assert list(corto.columns) == ["t_s", "clase"] and len(corto) == 3


@pytest.mark.parametrize("vel", [20.0, 3.0])
def test_detector_en_vivo_igual_al_de_lotes(vel):
    fs = 100
    rng = np.random.default_rng(2)
    a = rng.normal(0, 0.02, 3000)
    for i in (800, 1500, 1520, 2400):
        a[i:i + 3] += [0.8, -0.9, 0.5]
    lotes = list(detectar_umbral(a, np.full(a.size, vel), fs, ParametrosUmbral())["indice"])
    d = cp.DetectorEnVivo(fs)
    vivo = [n for n, x in enumerate(a) if d.muestra(float(x), vel) is not None]
    assert vivo == lotes
