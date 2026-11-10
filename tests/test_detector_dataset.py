"""Fase B: detector calibrable (YAML), evaluación por salida completa y dataset de ventanas. Datos SINTÉTICOS."""
import csv
import random
from pathlib import Path

import numpy as np
import pytest

from viaviva import detector, ventanas
from viaviva.senal import cargar


def _sesion(carpeta: Path, golpes, semilla: int, marcas=None, segundos=60, eje="z") -> Path:
    """Export tipo phyphox a 100 Hz, carro a 18 km/h. El celular puede estar acostado (gravedad en z) o de lado (y)."""
    carpeta.mkdir(parents=True)
    rnd = random.Random(semilla)
    with open(carpeta / "Accelerometer.csv", "w", encoding="utf-8") as f:
        f.write('"Time (s)","X (m/s^2)","Y (m/s^2)","Z (m/s^2)"\n')
        for i in range(int(segundos * 100)):
            t = i / 100
            golpe = 0.0
            for tg, amp in golpes:
                if abs(t - tg) < 0.05:
                    golpe = amp * 9.81 * (1 if t < tg else -0.6)
            vert = 9.81 + rnd.gauss(0, 0.25) + golpe
            x, y = rnd.gauss(0, 0.2), rnd.gauss(0, 0.2)
            z = vert
            if eje == "y":
                y, z = vert, y
            f.write(f"{t:.4f},{x:.4f},{y:.4f},{z:.4f}\n")
    with open(carpeta / "Location.csv", "w", encoding="utf-8") as f:
        f.write('"Time (s)","Latitude (°)","Longitude (°)","Height (m)","Velocity (m/s)","Direction (°)",'
                '"Horizontal Accuracy (m)","Vertical Accuracy (°)"\n')
        for s in range(segundos):
            f.write(f"{s},5.5350,{-73.37 + s * 0.000045:.6f},2800,5.0,90,4,3\n")
    if marcas is not None:
        with open(carpeta.parent / f"{carpeta.name}_etiquetas.csv", "w", encoding="utf-8") as f:
            f.write("t_s,clase\n" + "".join(f"{t},{c}\n" for t, c in marcas))
    return carpeta


@pytest.mark.parametrize("eje", ["z", "y"])
def test_detector_encuentra_golpes_con_cualquier_orientacion(tmp_path, eje):
    ses = _sesion(tmp_path / "s", [(10, 1.2), (25, 0.6), (40, 0.4)], 1, eje=eje)
    p = detector.cargar_parametros(detector.RUTA_CONFIG)
    ev = detector.detectar(cargar(ses), p)
    assert [round(e["t_s"]) for e in ev] == [10, 25, 40]
    assert [e["severidad"] for e in ev] == ["alta", "media", "baja"]
    assert all(0 < e["confianza"] < 1 and e["lat"] is not None for e in ev)


def test_evaluacion_y_calibracion_por_salida_sin_fugas(tmp_path):
    p = detector.cargar_parametros(detector.RUTA_CONFIG)
    senales = []
    for k in range(3):
        golpes = [(10 + 10 * i + k, 0.8) for i in range(4)]
        marcas = [(t + 0.4, "hueco") for t, _ in golpes[:3]] + [(55, "via_buena")]   # la 4.ª sin marcar = FP
        senales.append(cargar(_sesion(tmp_path / f"s{k}", golpes, k, marcas)))
    ev = detector.evaluar(senales, p)
    assert ev["global"] == {"tp": 9, "fp": 3, "fn": 0, "precision": 0.75, "exhaustividad": 1.0, "f1": 0.857}
    assert ev["por_clase"]["hueco"] == {"marcas": 9, "detectadas": 9, "exhaustividad": 1.0}
    val = detector.validar_dejando_una_fuera(senales, p)
    assert [x["prueba"] for x in val["pliegues"]] == ["s0", "s1", "s2"]
    assert val["global_prueba"]["tp"] + val["global_prueba"]["fn"] == 9
    assert "error" in detector.validar_dejando_una_fuera(senales[:1], p)     # una sola salida: no se calibra


def test_dataset_ventanas_etiquetas_y_calidad(tmp_path):
    ses = _sesion(tmp_path / "s", [(10, 1.0)], 3, [(10.2, "hueco"), (30, "via_buena")], segundos=40)
    salida = ventanas.construir([ses], salida=tmp_path / "out")
    with open(salida / "manifest.csv", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    assert len(filas) == 38                                   # 40 s (3 999 muestras), ventanas de 2 s cada 1 s
    assert set(ventanas.CARACTERISTICAS) <= set(filas[0])
    huecos = [w for w in filas if w["etiqueta"] == "hueco"]
    assert {float(w["t0_s"]) for w in huecos} <= {8.0, 9.0, 10.0, 11.0} and len(huecos) >= 2
    golpe = max(filas, key=lambda w: float(w["pico_v"]))
    assert golpe["etiqueta"] == "hueco" and float(golpe["pico_v"]) > 0.8
    assert "Desbalance" in (salida / "calidad.md").read_text(encoding="utf-8")


def test_clasificador_de_ventanas_por_salida(tmp_path):
    pytest.importorskip("sklearn")
    from viaviva.modelo_ventanas import manifest_sintetico
    m = manifest_sintetico(tmp_path / "m.csv", n=120)
    r = ventanas.evaluar(m)
    assert r["salidas"] == ["SINTETICO-0", "SINTETICO-1"] and np.array(r["matriz_confusion"]).sum() == 120
    assert r["por_clase"]["hueco"]["f1"] > 0.9               # clases bien separadas a propósito (SINTÉTICO)


def test_esqueleto_tflite_humo(tmp_path):
    pytest.importorskip("tensorflow")
    from viaviva.modelo_ventanas import entrenar, manifest_sintetico
    r = entrenar(manifest_sintetico(tmp_path / "m.csv"), epocas=3, salida=tmp_path / "mod", sintetico=True)
    assert (tmp_path / "mod" / "modelo_int8.tflite").exists() and r["kb_int8"] < 50
