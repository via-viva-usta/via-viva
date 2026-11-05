"""Clasificar UNA foto con el modelo int8 de dataset.modelo (lo usa el bot; también sirve por consola).

Solo necesita numpy, Pillow y un intérprete TFLite: ai-edge-litert (LiteRT, liviano) o, si no está, tensorflow.lite.
No importa pandas ni TensorFlow completo, para que el bot arranque rápido.

Uso: python -m dataset.clasificar data\\fotos_bot\\algo.jpg
"""
from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

SALIDAS = Path(__file__).resolve().parent / "salidas"


def _interprete(ruta: Path):
    try:
        from ai_edge_litert.interpreter import Interpreter
    except ImportError:
        from tensorflow.lite import Interpreter      # respaldo: TensorFlow completo
    it = Interpreter(model_path=str(ruta))
    it.allocate_tensors()
    return it


@lru_cache(maxsize=1)
def cargar(version: str | None = None):
    """(intérprete, info) del modelo más reciente (dataset/salidas/ultimo.txt) o de la versión pedida."""
    if version is None:
        ultimo = SALIDAS / "ultimo.txt"
        if not ultimo.exists():
            raise FileNotFoundError("no hay modelo de fotos entrenado (dataset/salidas/ultimo.txt)")
        version = ultimo.read_text(encoding="utf-8").strip()
    carpeta = SALIDAS / version
    info = json.loads((carpeta / "info.json").read_text(encoding="utf-8"))
    return _interprete(carpeta / info["tflite"]), info


def entrada(ruta: Path, lado: int) -> np.ndarray:
    """Igual que el entrenamiento: endereza por EXIF, escala sin deformar y rellena con negro centrado (uint8)."""
    img = ImageOps.exif_transpose(Image.open(ruta)).convert("RGB")
    k = lado / max(img.size)
    img = img.resize((max(1, round(img.width * k)), max(1, round(img.height * k))), Image.BILINEAR)
    lienzo = Image.new("RGB", (lado, lado))
    lienzo.paste(img, ((lado - img.width) // 2, (lado - img.height) // 2))
    return np.asarray(lienzo, dtype=np.uint8)[None]


def clasificar(ruta) -> dict:
    """{'clase', 'confianza', 'version', 'sintetico', 'probabilidades'}."""
    it, info = cargar()
    ent, sal = it.get_input_details()[0], it.get_output_details()[0]
    x = entrada(Path(ruta), info["tam"])
    if ent["dtype"] != np.uint8:                       # modelo float: la preparación depende de la arquitectura
        x = x.astype(np.float32)
        if info.get("arquitectura") == "mobilenetv2":
            x = x / 127.5 - 1
    it.set_tensor(ent["index"], x.astype(ent["dtype"]))
    it.invoke()
    p = it.get_tensor(sal["index"])[0].astype(np.float32)
    if sal["dtype"] == np.uint8:
        esc, cero = sal["quantization"]
        p = (p - cero) * esc
    p = p / max(float(p.sum()), 1e-9)
    k = int(np.argmax(p))
    return {"clase": info["clases"][k], "confianza": float(p[k]), "version": info["version"],
            "sintetico": bool(info.get("sintetico")), "probabilidades": dict(zip(info["clases"], map(float, p)))}


if __name__ == "__main__":
    for r in sys.argv[1:]:
        c = clasificar(r)
        print(f"{r}: {c['clase']} ({c['confianza']:.0%}) · modelo {c['version']}" + (" · SINTÉTICO" if c["sintetico"] else ""))
