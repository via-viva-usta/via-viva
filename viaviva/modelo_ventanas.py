"""Esqueleto del clasificador de ventanas para el borde (TFLite int8). ETAPA SIGUIENTE: no es un resultado.

    %USERPROFILE%\\.venvs\\vv-modelo\\Scripts\\python -m viaviva.modelo_ventanas <manifest.csv> [--sintetico]

Red densa pequeña sobre las características de `viaviva/ventanas.py` (normalizadas), validación dejando una salida
afuera para elegir épocas, y exportación a TFLite float32 e int8 (PTQ con 200 ventanas de entrenamiento). Se compara
contra el detector por umbrales con las mismas salidas cuando haya datos etiquetados suficientes (≥ 30 por clase).
`--sintetico` arma un manifest de prueba (marcado SINTETICO) solo para comprobar que el flujo corre.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime
from pathlib import Path

import numpy as np

from viaviva import config
from viaviva.ventanas import CARACTERISTICAS

os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
SALIDAS = config.RAIZ / "data" / "procesado" / "modelo_ventanas"


def leer(manifest: Path):
    with open(manifest, encoding="utf-8") as f:
        filas = [w for w in csv.DictReader(f) if w["estado"] == "ok" and w["etiqueta"] != "sin_marca"]
    X = np.array([[float(w[c]) if w[c] not in ("", "nan") else 0.0 for c in CARACTERISTICAS] for w in filas], np.float32)
    clases = sorted({w["etiqueta"] for w in filas})
    y = np.array([clases.index(w["etiqueta"]) for w in filas], np.int32)
    return X, y, clases, [w["sesion"] for w in filas]


def manifest_sintetico(ruta: Path, n: int = 300, semilla: int = 0) -> Path:
    rnd = np.random.default_rng(semilla)
    with open(ruta, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sesion", "estado", "etiqueta", *CARACTERISTICAS])
        for i in range(n):
            c = ["via_buena", "hueco", "resalto"][i % 3]
            base = {"via_buena": 0.05, "hueco": 0.6, "resalto": 0.35}[c]
            fila = rnd.normal(base, 0.05, len(CARACTERISTICAS)).round(4)
            w.writerow([f"SINTETICO-{i % 2}", "ok", c, *fila])
    return ruta


def entrenar(manifest: Path, epocas: int = 40, salida: Path | None = None, sintetico: bool = False) -> dict:
    import tensorflow as tf
    X, y, clases, sesiones = leer(manifest)
    if len(clases) < 2 or len(y) < 20:
        return {"error": f"Pocos datos: {len(y)} ventanas con marca y {len(clases)} clases. Etapa siguiente."}
    media, desv = X.mean(0), X.std(0) + 1e-6
    Xn = (X - media) / desv
    tf.random.set_seed(0)
    modelo = tf.keras.Sequential([tf.keras.layers.Input((X.shape[1],)), tf.keras.layers.Dense(16, activation="relu"),
                                  tf.keras.layers.Dense(len(clases), activation="softmax")])
    modelo.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    modelo.fit(Xn, y, epochs=epocas, verbose=0, batch_size=32)
    salida = Path(salida) if salida else SALIDAS / (datetime.now().strftime("%Y%m%d-%H%M") +
                                                     ("-SINTETICO" if sintetico else ""))
    salida.mkdir(parents=True, exist_ok=True)
    conv = tf.lite.TFLiteConverter.from_keras_model(modelo)
    (salida / "modelo_f32.tflite").write_bytes(conv.convert())
    conv = tf.lite.TFLiteConverter.from_keras_model(modelo)
    conv.optimizations = [tf.lite.Optimize.DEFAULT]
    conv.representative_dataset = lambda: ([Xn[i:i + 1]] for i in range(min(200, len(Xn))))
    conv.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    conv.inference_input_type = conv.inference_output_type = tf.int8
    (salida / "modelo_int8.tflite").write_bytes(conv.convert())
    info = {"clases": clases, "caracteristicas": CARACTERISTICAS, "media": media.tolist(), "desv": desv.tolist(),
            "n": int(len(y)), "salidas": sorted(set(sesiones)), "sintetico": sintetico,
            "exactitud_entrenamiento": round(float(modelo.evaluate(Xn, y, verbose=0)[1]), 3),
            "aviso": "Exactitud sobre el MISMO conjunto de entrenamiento: no es un resultado."}
    (salida / "info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"salida": str(salida), **{k: info[k] for k in ("n", "clases", "exactitud_entrenamiento", "aviso")},
            "kb_int8": round((salida / "modelo_int8.tflite").stat().st_size / 1024, 1)}


def main():
    ap = argparse.ArgumentParser(prog="viaviva modelo", description=__doc__.splitlines()[0])
    ap.add_argument("manifest", nargs="?")
    ap.add_argument("--sintetico", action="store_true")
    ap.add_argument("--epocas", type=int, default=40)
    a = ap.parse_args()
    ruta = Path(a.manifest) if a.manifest else None
    if a.sintetico:
        SALIDAS.mkdir(parents=True, exist_ok=True)
        ruta = manifest_sintetico(SALIDAS / "manifest_SINTETICO.csv")
    print(json.dumps(entrenar(ruta, a.epocas, sintetico=a.sintetico), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
