"""Clasificador de las 9 clases de fotos con transfer learning (MobileNetV3-Small, ImageNet) y exportación a TFLite int8.

Pasos:
  1. Toma las fotos etiquetadas de metadatos.csv (sin las EXCLUIDAS) y las agrupa por SITIO (dataset/comun.py: fotos
     del mismo punto a ≤ 15 m, o del mismo autor con ≤ 10 min sin GPS).
  2. Divide train / val / test POR SITIO (StratifiedGroupKFold): las 4-5 fotos de un mismo hueco quedan TODAS en el mismo
     lado. Dividir por foto inflaría las métricas (el modelo "reconoce el sitio", no la clase).
  3. Entrena la cabeza con la base congelada y luego ajusta el último tramo de la base (fine-tuning), con aumentos
     (volteo, rotación leve, brillo y contraste) y pesos por clase.
  4. Prueba: precisión, exhaustividad y F1 por clase, matriz de confusión y galería de errores.
  5. Exporta a TFLite float32 e int8 (cuantización entera completa con datos de calibración de train) y mide la
     exactitud del int8 en test para compararla con el modelo float.

Salida: <dataset>/modelo/<versión>/ (reporte.md, metricas.json, matriz_confusion.png, errores.png, division.csv,
modelo.keras, modelo_float32.tflite, modelo_int8.tflite, etiquetas.txt). Con --sintetico la versión dice SINTETICO.

TensorFlow no cabe en la ruta larga del repo (Windows sin rutas largas): va en un venv de ruta corta.
  py -3.11 -m venv %USERPROFILE%\\.venvs\\vv-modelo
  %USERPROFILE%\\.venvs\\vv-modelo\\Scripts\\python -m pip install -r dataset\\requirements-modelo.txt
Uso (desde via-viva/):
  %USERPROFILE%\\.venvs\\vv-modelo\\Scripts\\python -m dataset.modelo
  %USERPROFILE%\\.venvs\\vv-modelo\\Scripts\\python -m dataset.modelo --sintetico      (prueba del flujo)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import tensorflow as tf  # noqa: E402
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score  # noqa: E402
from sklearn.model_selection import StratifiedGroupKFold  # noqa: E402

from dataset.comun import CLASES, PROCESADO, PROCESADO_SINTETICO, ZONA_LOCAL, leer_metadatos, sitios  # noqa: E402

keras = tf.keras
TAM = 224
SEMILLA = 42
MIN_SITIOS_POR_CLASE = 3      # para que cada clase pueda aparecer en train y en test


def preparar(salida: Path) -> pd.DataFrame:
    m = leer_metadatos(salida / "metadatos.csv")
    m = m[m["clase"].isin(CLASES) & ~m["notas"].str.contains("EXCLUIR")].copy()
    m["ruta"] = [str(salida / a) for a in m["archivo"]]
    m = m[[Path(r).exists() for r in m["ruta"]]]
    m["sitio"] = sitios(m).to_numpy()
    m["y"] = m["clase"].map({c: i for i, c in enumerate(CLASES)})
    return m.reset_index(drop=True)


def dividir(m: pd.DataFrame, frac_test=0.15, frac_val=0.15) -> pd.Series:
    """train / val / test por sitio, estratificado por clase en lo posible."""
    split = pd.Series("train", index=m.index)
    sgk = StratifiedGroupKFold(n_splits=round(1 / frac_test), shuffle=True, random_state=SEMILLA)
    _, te = next(sgk.split(m, m["y"], m["sitio"]))
    split.iloc[te] = "test"
    resto = m[split == "train"]
    sgk = StratifiedGroupKFold(n_splits=round((1 - frac_test) / frac_val), shuffle=True, random_state=SEMILLA)
    _, va = next(sgk.split(resto, resto["y"], resto["sitio"]))
    split.loc[resto.index[va]] = "val"
    for a in ("train", "val", "test"):                      # ningún sitio puede quedar en dos lados
        for b in ("train", "val", "test"):
            if a < b:
                comun = set(m.loc[split == a, "sitio"]) & set(m.loc[split == b, "sitio"])
                assert not comun, f"sitios en {a} y {b}: {comun}"
    return split


def cargar(ruta, y):
    img = tf.io.decode_jpeg(tf.io.read_file(ruta), channels=3)
    img = tf.image.resize_with_pad(img, TAM, TAM)          # sin deformar; valores 0-255 (la red normaliza adentro)
    return img, y


def datos(df: pd.DataFrame, lote: int, mezclar: bool) -> tf.data.Dataset:
    ds = tf.data.Dataset.from_tensor_slices((df["ruta"].tolist(), df["y"].to_numpy()))
    if mezclar:
        ds = ds.shuffle(len(df), seed=SEMILLA, reshuffle_each_iteration=True)
    return ds.map(cargar, num_parallel_calls=tf.data.AUTOTUNE).batch(lote).prefetch(tf.data.AUTOTUNE)


def construir(con_pesos: bool, minimalista: bool = False) -> tuple[keras.Model, keras.Model, keras.Model]:
    """(modelo de entrenamiento con aumentos, modelo de inferencia SIN aumentos, base). Los dos comparten capas y
    pesos; el de inferencia es el que se guarda y se exporta (TFLite no tiene las operaciones aleatorias)."""
    base = keras.applications.MobileNetV3Small(input_shape=(TAM, TAM, 3), include_top=False,
                                               weights="imagenet" if con_pesos else None,
                                               include_preprocessing=True,   # entra 0-255
                                               minimalistic=minimalista)
    base.trainable = False
    aumento = keras.Sequential([keras.layers.RandomFlip("horizontal"), keras.layers.RandomRotation(0.04),
                                keras.layers.RandomBrightness(0.2, value_range=(0, 255)),
                                keras.layers.RandomContrast(0.2)], name="aumento")
    gap = keras.layers.GlobalAveragePooling2D()
    abandono = keras.layers.Dropout(0.3)
    densa = keras.layers.Dense(len(CLASES), activation="softmax")

    def cabeza(x):
        return densa(abandono(gap(base(x, training=False))))

    x_in = keras.Input((TAM, TAM, 3))
    x_inf = keras.Input((TAM, TAM, 3))
    return keras.Model(x_in, cabeza(aumento(x_in))), keras.Model(x_inf, cabeza(x_inf)), base


def entrenar(modelo, base, tr, va, pesos_clase, ep_cabeza, ep_ajuste):
    parar = keras.callbacks.EarlyStopping(monitor="val_loss", patience=4, restore_best_weights=True)
    modelo.compile(optimizer=keras.optimizers.Adam(1e-3), loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    h1 = modelo.fit(tr, validation_data=va, epochs=ep_cabeza, class_weight=pesos_clase, callbacks=[parar], verbose=2)
    hist = {k: list(v) for k, v in h1.history.items()}
    if ep_ajuste > 0:
        base.trainable = True
        corte = int(len(base.layers) * 0.7)                 # solo el último 30 % de la base
        for capa in base.layers[:corte]:
            capa.trainable = False
        for capa in base.layers:                            # BatchNorm congelada: con pocos datos se desestabiliza
            if isinstance(capa, keras.layers.BatchNormalization):
                capa.trainable = False
        modelo.compile(optimizer=keras.optimizers.Adam(1e-4), loss="sparse_categorical_crossentropy", metrics=["accuracy"])
        h2 = modelo.fit(tr, validation_data=va, epochs=ep_ajuste, class_weight=pesos_clase, callbacks=[parar],
                        verbose=2)
        for k, v in h2.history.items():
            hist[k] = hist.get(k, []) + list(v)
    return hist


def exportar_tflite(modelo, tr_df: pd.DataFrame, carpeta: Path) -> dict:
    guardado = carpeta / "saved_model"
    modelo.export(str(guardado), verbose=False)             # Keras 3 → SavedModel (lo que entiende el convertidor)
    conv = tf.lite.TFLiteConverter.from_saved_model(str(guardado))
    (carpeta / "modelo_float32.tflite").write_bytes(conv.convert())

    calib = tr_df.sample(min(200, len(tr_df)), random_state=SEMILLA)["ruta"].tolist()

    def representativo():
        for r in calib:
            img, _ = cargar(r, 0)
            yield [tf.cast(img[None], tf.float32)]

    conv = tf.lite.TFLiteConverter.from_saved_model(str(guardado))
    conv.optimizations = [tf.lite.Optimize.DEFAULT]
    conv.representative_dataset = representativo
    conv.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    conv.inference_input_type = tf.uint8                    # la foto entra tal cual (0-255)
    conv.inference_output_type = tf.uint8
    (carpeta / "modelo_int8.tflite").write_bytes(conv.convert())
    return {k: (carpeta / f"modelo_{k}.tflite").stat().st_size for k in ("float32", "int8")}


def predecir_tflite(ruta_modelo: Path, rutas: list[str]) -> np.ndarray:
    def interprete(**kw):
        i = tf.lite.Interpreter(model_path=str(ruta_modelo), **kw)
        i.resize_tensor_input(i.get_input_details()[0]["index"], [1, TAM, TAM, 3])   # el lote viene dinámico
        i.allocate_tensors()
        return i

    try:
        it = interprete()
    except RuntimeError:          # el delegado XNNPACK no siempre prepara el modelo int8: núcleos de referencia
        it = interprete(experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES)
    ent, sal = it.get_input_details()[0], it.get_output_details()[0]
    salida = []
    for r in rutas:
        img, _ = cargar(r, 0)
        x = img.numpy()[None]
        if ent["dtype"] == np.uint8:
            x = np.clip(np.round(x), 0, 255).astype(np.uint8)
        it.set_tensor(ent["index"], x.astype(ent["dtype"]))
        it.invoke()
        y = it.get_tensor(sal["index"])[0].astype(np.float32)
        if sal["dtype"] == np.uint8:
            esc, cero = sal["quantization"]
            y = (y - cero) * esc
        salida.append(y)
    return np.array(salida)


def figura_confusion(cm: np.ndarray, ruta: Path, titulo: str) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 6.5))
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(CLASES)), [c.replace("_", "\n") for c in CLASES], fontsize=8)
    ax.set_yticks(range(len(CLASES)), CLASES, fontsize=8)
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            if cm[i, j]:
                ax.text(j, i, cm[i, j], ha="center", va="center", fontsize=9,
                        color="white" if cm[i, j] > cm.max() / 2 else "black")
    ax.set_xlabel("predicha")
    ax.set_ylabel("verdadera")
    ax.set_title(titulo, fontsize=10)
    fig.tight_layout()
    fig.savefig(ruta, dpi=130)
    plt.close(fig)


def figura_errores(te: pd.DataFrame, pred: np.ndarray, prob: np.ndarray, ruta: Path, titulo: str) -> int:
    malas = te[pred != te["y"].to_numpy()].copy()
    malas["pred"] = pred[pred != te["y"].to_numpy()]
    malas["conf"] = prob[pred != te["y"].to_numpy()].max(1)
    malas = malas.sort_values("conf", ascending=False).head(16)
    if malas.empty:
        return 0
    n = len(malas)
    cols = min(4, n)
    filas = (n + cols - 1) // cols
    fig, axs = plt.subplots(filas, cols, figsize=(3.2 * cols, 3 * filas), squeeze=False)
    for ax in axs.ravel():
        ax.axis("off")
    for ax, (_, f) in zip(axs.ravel(), malas.iterrows()):
        ax.imshow(plt.imread(f["ruta"]))
        ax.set_title(f"real: {f['clase']}\npredijo: {CLASES[f['pred']]} ({f['conf']:.0%})", fontsize=8)
    fig.suptitle(titulo, fontsize=10)
    fig.tight_layout()
    fig.savefig(ruta, dpi=110)
    plt.close(fig)
    return len(malas)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, default=None)
    ap.add_argument("--sintetico", action="store_true")
    ap.add_argument("--epocas-cabeza", type=int, default=15)
    ap.add_argument("--epocas-ajuste", type=int, default=10)
    ap.add_argument("--lote", type=int, default=16)
    ap.add_argument("--minimalista", action="store_true",
                    help="MobileNetV3-Small minimalista (sin hard-swish ni SE): cuantiza mejor a int8")
    ap.add_argument("--sin-pesos", action="store_true", help="sin pesos de ImageNet (si no hay internet): solo prueba")
    a = ap.parse_args()
    salida = a.salida or (PROCESADO_SINTETICO if a.sintetico else PROCESADO)
    tf.keras.utils.set_random_seed(SEMILLA)

    m = preparar(salida)
    por_clase = m.groupby("clase")["sitio"].nunique().reindex(CLASES, fill_value=0)
    pocas = por_clase[por_clase < MIN_SITIOS_POR_CLASE]
    if len(pocas):
        sys.exit(f"Faltan sitios etiquetados (mínimo {MIN_SITIOS_POR_CLASE} por clase): "
                 + ", ".join(f"{c} = {n}" for c, n in pocas.items()))
    m["split"] = dividir(m).to_numpy()
    sint = "SINTETICO" if a.sintetico or m["notas"].str.contains("SINTETICO").any() else ""
    version = f"{datetime.now(ZONA_LOCAL):%Y%m%d-%H%M}" + (f"-{sint}" if sint else "") + ("-SINPESOS" if a.sin_pesos else "") + ("-MIN" if a.minimalista else "")
    carpeta = salida / "modelo" / version
    carpeta.mkdir(parents=True, exist_ok=True)
    m[["id", "clase", "sitio", "split"]].to_csv(carpeta / "division.csv", index=False)
    resumen = m.groupby(["split", "clase"]).size().unstack(0).reindex(CLASES).fillna(0).astype(int)
    print(f"Versión {version}. Fotos por clase y lado (sitios separados):\n{resumen}")

    tr, va, te = (m[m["split"] == s] for s in ("train", "val", "test"))
    conteo = tr["y"].value_counts()
    pesos_clase = {int(k): len(tr) / (len(CLASES) * v) for k, v in conteo.items()}
    modelo, inferencia, base = construir(not a.sin_pesos, a.minimalista)
    hist = entrenar(modelo, base, datos(tr, a.lote, True), datos(va, a.lote, False), pesos_clase,
                    a.epocas_cabeza, a.epocas_ajuste)
    inferencia.save(carpeta / "modelo.keras")

    prob = inferencia.predict(datos(te, a.lote, False), verbose=0)
    pred = prob.argmax(1)
    y = te["y"].to_numpy()
    rep = classification_report(y, pred, labels=range(len(CLASES)), target_names=CLASES, output_dict=True,
                                zero_division=0)
    cm = confusion_matrix(y, pred, labels=range(len(CLASES)))
    aviso = " — SINTÉTICO: prueba del flujo, NO es resultado" if sint else ""
    figura_confusion(cm, carpeta / "matriz_confusion.png", f"Matriz de confusión (test, {len(te)} fotos){aviso}")
    n_err = figura_errores(te, pred, prob, carpeta / "errores.png", f"Errores más confiados en test{aviso}")

    tamanos = exportar_tflite(inferencia, tr, carpeta)
    pred8 = predecir_tflite(carpeta / "modelo_int8.tflite", te["ruta"].tolist()).argmax(1)
    (carpeta / "etiquetas.txt").write_text("\n".join(CLASES) + "\n", encoding="utf-8")

    met = {"version": version, "sintetico": bool(sint), "minimalista": a.minimalista, "pesos_imagenet": not a.sin_pesos,
           "fotos": {s: int((m["split"] == s).sum()) for s in ("train", "val", "test")},
           "sitios": {s: int(m.loc[m["split"] == s, "sitio"].nunique()) for s in ("train", "val", "test")},
           "exactitud_test_float": accuracy_score(y, pred), "f1_macro_test_float": f1_score(y, pred, average="macro"),
           "exactitud_test_int8": accuracy_score(y, pred8), "f1_macro_test_int8": f1_score(y, pred8, average="macro"),
           "acuerdo_float_int8": float((pred == pred8).mean()),
           "tamano_bytes": tamanos, "por_clase": {c: rep[c] for c in CLASES}, "matriz_confusion": cm.tolist(),
           "epocas": len(hist.get("loss", []))}
    (carpeta / "metricas.json").write_text(json.dumps(met, indent=2, ensure_ascii=False), encoding="utf-8")

    l = [f"# Modelo de fotos {version}{aviso}", "",
         f"MobileNetV3-Small{' minimalista' if a.minimalista else ''} {'con' if not a.sin_pesos else 'SIN'} pesos de ImageNet, {TAM}×{TAM}, "
         f"{met['epocas']} épocas. División por SITIO: "
         + ", ".join(f"{s} {met['fotos'][s]} fotos / {met['sitios'][s]} sitios" for s in ("train", "val", "test")), "",
         "| | Exactitud test | F1 macro test | Tamaño |", "|---|---|---|---|",
         f"| float32 (Keras/TFLite) | {met['exactitud_test_float']:.3f} | {met['f1_macro_test_float']:.3f} | "
         f"{tamanos['float32'] / 1024:.0f} KB |",
         f"| int8 (TFLite) | {met['exactitud_test_int8']:.3f} | {met['f1_macro_test_int8']:.3f} | "
         f"{tamanos['int8'] / 1024:.0f} KB |", "",
         f"Acuerdo float vs. int8 en test: {met['acuerdo_float_int8']:.1%}.", "",
         "| Clase | Precisión | Exhaustividad | F1 | Fotos en test |", "|---|---|---|---|---|"]
    l += [f"| {c} | {rep[c]['precision']:.2f} | {rep[c]['recall']:.2f} | {rep[c]['f1-score']:.2f} | "
          f"{int(rep[c]['support'])} |" for c in CLASES]
    l += ["", f"Matriz de confusión: `matriz_confusion.png`. Errores ({n_err} mostrados): `errores.png`."]
    (carpeta / "reporte.md").write_text("\n".join(l) + "\n", encoding="utf-8")
    print("\n".join(l))
    print(f"\nTodo en {carpeta}")


if __name__ == "__main__":
    main()
