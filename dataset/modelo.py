"""Clasificador de las 9 clases de fotos: transfer learning, aumentos para Tunja, cuantización int8 (PTQ y QAT) y Grad-CAM.

Pasos:
  1. Fotos etiquetadas de metadatos.csv (sin las EXCLUIDAS), agrupadas por SITIO (dataset/comun.py).
  2. División train / val / test POR SITIO (StratifiedGroupKFold): las fotos de un mismo punto quedan del mismo lado.
  3. (Opcional) pre-entrenamiento con recortes externos hueco / no_hueco (dataset/externos.py --recortes): tarea
     auxiliar que ajusta la base antes de las 9 clases. La evaluación es SIEMPRE con nuestras fotos.
  4. Entrenamiento: cabeza con la base congelada + ajuste fino del último 30 %, pesos por clase y aumentos pensados
     para Tunja (en tf.data, solo en train): noche, piso mojado, sombras duras, desenfoque leve, perspectiva, brillo.
  5. Prueba: precisión, exhaustividad y F1 por clase, F1 macro, matriz de confusión, errores y Grad-CAM.
  6. TFLite: float32; int8 PTQ calibrado con 200 fotos de train; int8 PTQ con 1000 muestras AUMENTADAS; e int8 QAT
     (entrenamiento consciente de la cuantización, solo MobileNetV2: las hard-swish de MobileNetV3 no las cuantiza
     tensorflow-model-optimization). Para cada uno: exactitud, F1 macro, tamaño y latencia (en el PC).

Arquitecturas: mobilenetv3 (MobileNetV3-Small, por defecto) y mobilenetv2 (MobileNetV2 α=1). --comparar entrena las dos y
hace la tabla float32 vs. int8 PTQ vs. int8 QAT.

Salida: dataset/salidas/<versión>/ (ignorada por Git): reporte.md, metricas.json, matriz_confusion.png, errores.png,
gradcam.png, division.csv, <arq>/modelo.keras y *.tflite, info.json (para la página del celular y el bot).
dataset/salidas/ultimo.txt apunta a la última versión. Con fotos sintéticas la versión dice SINTETICO.

TensorFlow va en un venv de ruta corta (rutas largas de Windows) y con las versiones que deja pasar Smart App Control:
  py -3.11 -m venv %USERPROFILE%\\.venvs\\vv-modelo
  %USERPROFILE%\\.venvs\\vv-modelo\\Scripts\\python -m pip install -r dataset\\requirements-modelo.txt
Uso (desde via-viva/):
  %USERPROFILE%\\.venvs\\vv-modelo\\Scripts\\python -m dataset.modelo                       (fotos reales)
  %USERPROFILE%\\.venvs\\vv-modelo\\Scripts\\python -m dataset.modelo --sintetico --comparar (prueba del flujo)
  ... --preentrenar data\\externo\\kaggle_potholes                                          (con recortes externos)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ["TF_USE_LEGACY_KERAS"] = "1"          # tf_keras (Keras 2): lo exige tensorflow-model-optimization para QAT

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import tensorflow as tf  # noqa: E402
import tf_keras as keras  # noqa: E402
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score  # noqa: E402
from sklearn.model_selection import StratifiedGroupKFold  # noqa: E402

from dataset.comun import CLASES, PROCESADO, PROCESADO_SINTETICO, RAIZ, ZONA_LOCAL, leer_metadatos, sitios  # noqa: E402

TAM = 224
SEMILLA = 42
MIN_SITIOS_POR_CLASE = 3
SALIDAS = RAIZ / "dataset" / "salidas"
ARQ = {   # entrada: lo que recibe la red después de la preparación (el TFLite int8 recibe la foto 0-255 en uint8)
    "mobilenetv3": {"entrada": "0-255", "qat": False},
    "mobilenetv2": {"entrada": "-1..1", "qat": True},
}


# ---------------------------------------------------------------- datos
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
    img = tf.io.decode_image(tf.io.read_file(ruta), channels=3, expand_animations=False)
    img = tf.image.resize_with_pad(tf.cast(img, tf.float32), TAM, TAM)    # sin deformar; 0-255
    return img, y


def preparar_entrada(img, arq: str):
    return img / 127.5 - 1.0 if ARQ[arq]["entrada"] == "-1..1" else img


def _si(p):
    return tf.random.uniform([]) < p


def aumentar(img):
    """Aumentos pensados para Tunja (solo train). img: [224, 224, 3] float 0-255."""
    img = tf.image.random_flip_left_right(img)
    # rotación leve + perspectiva (celular no paralelo al piso)
    ang = tf.random.uniform([], -0.07, 0.07)
    c, s, m = tf.cos(ang), tf.sin(ang), TAM / 2
    p = tf.random.uniform([2], -6e-4, 6e-4)
    t = tf.stack([c, -s, m - c * m + s * m, s, c, m - s * m - c * m, p[0], p[1]])[None]
    img = tf.raw_ops.ImageProjectiveTransformV3(images=img[None], transforms=t, output_shape=[TAM, TAM],
                                                fill_value=0.0, interpolation="BILINEAR", fill_mode="REFLECT")[0]
    img = tf.image.random_brightness(img, 25.0)
    img = tf.image.random_contrast(img, 0.75, 1.25)
    yy, xx = tf.meshgrid(tf.range(TAM, dtype=tf.float32), tf.range(TAM, dtype=tf.float32), indexing="ij")
    # sombra dura: un semiplano oscurecido (poste, árbol, edificio)
    def sombra(x):
        a = tf.random.uniform([], 0, 2 * np.pi)
        x0, y0 = tf.random.uniform([2], 0, TAM)[0], tf.random.uniform([2], 0, TAM)[1]
        lado = tf.cast((xx - x0) * tf.cos(a) + (yy - y0) * tf.sin(a) > 0, tf.float32)
        return x * (1 - lado[..., None] * tf.random.uniform([], 0.35, 0.55))
    img = tf.cond(_si(0.3), lambda: sombra(img), lambda: img)
    # noche: oscura, azulada y con ruido del sensor
    def noche(x):
        x = x * tf.random.uniform([], 0.2, 0.45) * tf.constant([0.85, 0.9, 1.15])
        return x + tf.random.normal(tf.shape(x), 0, 6)
    img = tf.cond(_si(0.2), lambda: noche(img), lambda: img)
    # piso mojado: más oscuro, menos saturado y con reflejos
    def mojado(x):
        x = tf.image.adjust_saturation(x * 0.8, 0.6)
        brillo = tf.zeros([TAM, TAM])
        for _ in range(3):
            cx, cy = tf.random.uniform([], 0, TAM), tf.random.uniform([], 0, TAM)
            sx, sy = tf.random.uniform([], 10, 40), tf.random.uniform([], 3, 12)
            brillo += tf.exp(-(((xx - cx) / sx) ** 2 + ((yy - cy) / sy) ** 2))
        return x + 110 * brillo[..., None]
    img = tf.cond(_si(0.2), lambda: mojado(img), lambda: img)
    # desenfoque leve (movimiento de la mano, lente sucio)
    def desenfoque(x):
        sig = tf.random.uniform([], 0.8, 1.8)
        k = tf.exp(-tf.range(-3.0, 4.0) ** 2 / (2 * sig ** 2))
        k = k / tf.reduce_sum(k)
        k2 = (k[:, None] * k[None, :])[:, :, None, None] * tf.ones([1, 1, 3, 1])
        return tf.nn.depthwise_conv2d(x[None], k2, [1, 1, 1, 1], "SAME")[0]
    img = tf.cond(_si(0.2), lambda: desenfoque(img), lambda: img)
    return tf.clip_by_value(img, 0, 255)


def datos(df: pd.DataFrame, lote: int, arq: str, mezclar=False, aumentos=False, repetir=1) -> tf.data.Dataset:
    ds = tf.data.Dataset.from_tensor_slices((df["ruta"].tolist(), df["y"].to_numpy()))
    if repetir > 1:
        ds = ds.repeat(repetir)
    if mezclar:
        ds = ds.shuffle(len(df) * repetir, seed=SEMILLA, reshuffle_each_iteration=True)
    ds = ds.map(cargar, num_parallel_calls=tf.data.AUTOTUNE)
    if aumentos:
        ds = ds.map(lambda x, y: (aumentar(x), y), num_parallel_calls=tf.data.AUTOTUNE)
    ds = ds.map(lambda x, y: (preparar_entrada(x, arq), y), num_parallel_calls=tf.data.AUTOTUNE)
    return ds.batch(lote).prefetch(tf.data.AUTOTUNE)


# ---------------------------------------------------------------- modelo
def base_de(arq: str, con_pesos: bool) -> keras.Model:
    w = "imagenet" if con_pesos else None
    if arq == "mobilenetv3":
        b = keras.applications.MobileNetV3Small(input_shape=(TAM, TAM, 3), include_top=False, weights=w,
                                                include_preprocessing=True)
    else:
        b = keras.applications.MobileNetV2(input_shape=(TAM, TAM, 3), include_top=False, weights=w)
    b.trainable = False
    return b


def cabeza(base, n: int, nombre: str) -> keras.Model:
    """Modelo plano (sin submodelos: lo exige la QAT) = base + promedio global + dropout + densa."""
    x = keras.layers.GlobalAveragePooling2D(name=f"gap_{nombre}")(base.output)
    x = keras.layers.Dropout(0.3, name=f"drop_{nombre}")(x)
    return keras.Model(base.input, keras.layers.Dense(n, activation="softmax", name=nombre)(x))


def descongelar(base, fraccion=0.3):
    base.trainable = True
    corte = int(len(base.layers) * (1 - fraccion))
    for i, capa in enumerate(base.layers):
        capa.trainable = i >= corte and not isinstance(capa, keras.layers.BatchNormalization)


def entrenar(modelo, base, tr, va, pesos, ep_cabeza, ep_ajuste, lr=1e-3):
    parar = keras.callbacks.EarlyStopping(monitor="val_loss", patience=4, restore_best_weights=True)
    modelo.compile(optimizer=keras.optimizers.Adam(lr), loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    h = modelo.fit(tr, validation_data=va, epochs=ep_cabeza, class_weight=pesos, callbacks=[parar], verbose=2)
    n = len(h.history["loss"])
    if ep_ajuste > 0:
        descongelar(base)
        modelo.compile(optimizer=keras.optimizers.Adam(lr / 10), loss="sparse_categorical_crossentropy",
                       metrics=["accuracy"])
        h = modelo.fit(tr, validation_data=va, epochs=ep_ajuste, class_weight=pesos, callbacks=[parar], verbose=2)
        n += len(h.history["loss"])
    base.trainable = False
    return n


def preentrenar(base, carpeta: Path, arq: str, lote: int, epocas: int) -> dict:
    """Tarea auxiliar hueco / no_hueco con recortes externos; deja la base ajustada."""
    rec = carpeta / "_recortes"
    filas = [(str(p), int(c == "hueco")) for c in ("hueco", "no_hueco") for p in sorted((rec / c).glob("*.jpg"))]
    if len(filas) < 50:
        sys.exit(f"Muy pocos recortes en {rec}: correr antes dataset.externos --recortes {carpeta}")
    df = pd.DataFrame(filas, columns=["ruta", "y"]).sample(frac=1, random_state=SEMILLA)
    corte = int(0.85 * len(df))
    aux = cabeza(base, 2, "aux")
    n = entrenar(aux, base, datos(df[:corte], lote, arq, True, True), datos(df[corte:], lote, arq), None,
                 epocas, epocas, lr=1e-3)
    _, exac = aux.evaluate(datos(df[corte:], lote, arq), verbose=0)
    return {"recortes": len(df), "epocas": n, "exactitud_val_aux": float(exac), "origen": str(carpeta)}


# ---------------------------------------------------------------- TFLite
def representativo(df: pd.DataFrame, arq: str, n: int, con_aumentos: bool):
    ds = datos(df, 1, arq, mezclar=True, aumentos=con_aumentos, repetir=max(1, -(-n // len(df)))).take(n)

    def gen():
        for x, _ in ds:
            yield [tf.cast(x, tf.float32)]
    return gen


def a_tflite(modelo, ruta: Path, rep=None) -> int:
    conv = tf.lite.TFLiteConverter.from_keras_model(modelo)
    if rep is not None:
        conv.optimizations = [tf.lite.Optimize.DEFAULT]
        conv.representative_dataset = rep
        conv.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
        conv.inference_input_type = tf.uint8
        conv.inference_output_type = tf.uint8
    ruta.write_bytes(conv.convert())
    return ruta.stat().st_size


def predecir_tflite(ruta: Path, df: pd.DataFrame, arq: str) -> tuple[np.ndarray, float]:
    """(probabilidades, ms por foto). La latencia es en el PC con XNNPACK: NO es la del celular."""
    def interprete(**kw):
        i = tf.lite.Interpreter(model_path=str(ruta), **kw)
        i.resize_tensor_input(i.get_input_details()[0]["index"], [1, TAM, TAM, 3])
        i.allocate_tensors()
        return i
    try:
        it = interprete()
    except RuntimeError:
        it = interprete(experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES)
    ent, sal = it.get_input_details()[0], it.get_output_details()[0]
    salida, tiempos = [], []
    for x, _ in datos(df, 1, arq):
        x = x.numpy()
        if ent["dtype"] == np.uint8:
            esc, cero = ent["quantization"]
            x = np.clip(np.round(x / esc + cero), 0, 255).astype(np.uint8)
        it.set_tensor(ent["index"], x.astype(ent["dtype"]))
        t0 = time.perf_counter()
        it.invoke()
        tiempos.append((time.perf_counter() - t0) * 1000)
        y = it.get_tensor(sal["index"])[0].astype(np.float32)
        if sal["dtype"] == np.uint8:
            esc, cero = sal["quantization"]
            y = (y - cero) * esc
        salida.append(y)
    return np.array(salida), float(np.median(tiempos[1:] or tiempos))


def qat(modelo, tr, va, epocas: int):
    import tensorflow_model_optimization as tfmot
    q = tfmot.quantization.keras.quantize_model(modelo)
    q.compile(optimizer=keras.optimizers.Adam(1e-5), loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    q.fit(tr, validation_data=va, epochs=epocas, verbose=2)
    return q


# ---------------------------------------------------------------- figuras
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


def figura_errores(te, pred, prob, ruta: Path, titulo: str) -> int:
    malas = te[pred != te["y"].to_numpy()].copy()
    malas["pred"] = pred[pred != te["y"].to_numpy()]
    malas["conf"] = prob[pred != te["y"].to_numpy()].max(1)
    malas = malas.sort_values("conf", ascending=False).head(16)
    if malas.empty:
        return 0
    cols = min(4, len(malas))
    filas = -(-len(malas) // cols)
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


def gradcam(modelo, df: pd.DataFrame, arq: str, ruta: Path, titulo: str, n=8) -> None:
    """Mapa de calor de qué regiones empujaron la clase predicha (Selvaraju et al., 2017)."""
    capa = next(c for c in modelo.layers if c.name.startswith("gap_"))
    g = keras.Model(modelo.input, [capa.input, modelo.output])
    muestra = df.sample(min(n, len(df)), random_state=SEMILLA)
    cols = min(4, len(muestra))
    filas = -(-len(muestra) // cols)
    fig, axs = plt.subplots(filas, cols, figsize=(3.2 * cols, 3.1 * filas), squeeze=False)
    for ax in axs.ravel():
        ax.axis("off")
    for ax, (_, f) in zip(axs.ravel(), muestra.iterrows()):
        img, _ = cargar(f["ruta"], 0)
        x = preparar_entrada(img, arq)[None]
        with tf.GradientTape() as cinta:
            mapa, p = g(x)
            k = int(tf.argmax(p[0]))
            puntaje = p[:, k]
        grad = cinta.gradient(puntaje, mapa)[0]
        calor = tf.nn.relu(tf.reduce_sum(mapa[0] * tf.reduce_mean(grad, axis=(0, 1)), -1)).numpy()
        calor = calor / (calor.max() + 1e-8)
        calor = tf.image.resize(calor[..., None], (TAM, TAM)).numpy()[..., 0]
        ax.imshow(img.numpy().astype(np.uint8))
        ax.imshow(calor, cmap="jet", alpha=0.4)
        ax.set_title(f"real: {f['clase']}\npredijo: {CLASES[k]} ({float(p[0, k]):.0%})", fontsize=8)
    fig.suptitle(titulo, fontsize=10)
    fig.tight_layout()
    fig.savefig(ruta, dpi=110)
    plt.close(fig)


# ---------------------------------------------------------------- una arquitectura completa
def correr(arq, m, a, carpeta, aviso) -> dict:
    tr, va, te = (m[m["split"] == s] for s in ("train", "val", "test"))
    sub = carpeta / arq
    sub.mkdir(parents=True, exist_ok=True)
    keras.utils.set_random_seed(SEMILLA)
    base = base_de(arq, not a.sin_pesos)
    pre = preentrenar(base, a.preentrenar, arq, a.lote, a.epocas_pre) if a.preentrenar else None
    modelo = cabeza(base, len(CLASES), "clases")
    conteo = tr["y"].value_counts()
    pesos = {int(k): len(tr) / (len(CLASES) * v) for k, v in conteo.items()}
    d_tr, d_va = datos(tr, a.lote, arq, True, True), datos(va, a.lote, arq)
    epocas = entrenar(modelo, base, d_tr, d_va, pesos, a.epocas_cabeza, a.epocas_ajuste)
    modelo.save(sub / "modelo.keras")
    y = te["y"].to_numpy()
    prob = modelo.predict(datos(te, a.lote, arq), verbose=0)
    pred = prob.argmax(1)
    res = {"arquitectura": arq, "entrada": ARQ[arq]["entrada"], "epocas": epocas, "preentrenamiento": pre,
           "por_clase": classification_report(y, pred, labels=range(len(CLASES)), target_names=CLASES,
                                              output_dict=True, zero_division=0),
           "matriz_confusion": confusion_matrix(y, pred, labels=range(len(CLASES))).tolist(), "variantes": {}}
    figura_confusion(np.array(res["matriz_confusion"]), sub / "matriz_confusion.png",
                     f"{arq} · test {len(te)} fotos{aviso}")
    res["errores_mostrados"] = figura_errores(te, pred, prob, sub / "errores.png", f"{arq}: errores más confiados{aviso}")
    gradcam(modelo, te, arq, sub / "gradcam.png", f"{arq}: Grad-CAM (qué miró la red){aviso}")

    variantes = [("float32", None), ("int8_ptq_200", representativo(tr, arq, 200, False)),
                 ("int8_ptq_1000aug", representativo(tr, arq, 1000, True))]
    for nombre, rep in variantes:
        tam = a_tflite(modelo, sub / f"modelo_{nombre}.tflite", rep)
        p8, ms = predecir_tflite(sub / f"modelo_{nombre}.tflite", te, arq)
        res["variantes"][nombre] = {"tamano_kb": round(tam / 1024), "latencia_ms_pc": round(ms, 2),
                                    "exactitud": accuracy_score(y, p8.argmax(1)),
                                    "f1_macro": f1_score(y, p8.argmax(1), average="macro"),
                                    "acuerdo_con_keras": float((p8.argmax(1) == pred).mean()),
                                    "f1_por_clase": dict(zip(CLASES, f1_score(y, p8.argmax(1), labels=range(len(CLASES)),
                                                                         average=None, zero_division=0).tolist()))}
    if ARQ[arq]["qat"] and a.epocas_qat > 0:
        q = qat(modelo, d_tr, d_va, a.epocas_qat)
        tam = a_tflite(q, sub / "modelo_int8_qat.tflite", representativo(tr, arq, 200, False))
        p8, ms = predecir_tflite(sub / "modelo_int8_qat.tflite", te, arq)
        res["variantes"]["int8_qat"] = {"tamano_kb": round(tam / 1024), "latencia_ms_pc": round(ms, 2),
                                        "exactitud": accuracy_score(y, p8.argmax(1)),
                                        "f1_macro": f1_score(y, p8.argmax(1), average="macro"),
                                        "acuerdo_con_keras": float((p8.argmax(1) == pred).mean()),
                                    "f1_por_clase": dict(zip(CLASES, f1_score(y, p8.argmax(1), labels=range(len(CLASES)),
                                                                         average=None, zero_division=0).tolist()))}
    res["keras"] = {"exactitud": accuracy_score(y, pred), "f1_macro": f1_score(y, pred, average="macro")}
    return res


def mejor_int8(res: dict) -> str:
    v = {k: x for k, x in res["variantes"].items() if k.startswith("int8")}
    return max(v, key=lambda k: (v[k]["f1_macro"], -v[k]["tamano_kb"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, default=None, help="carpeta del dataset (data/procesado)")
    ap.add_argument("--sintetico", action="store_true")
    ap.add_argument("--arquitectura", choices=list(ARQ), default="mobilenetv3")
    ap.add_argument("--comparar", action="store_true", help="entrena mobilenetv3 y mobilenetv2 (con QAT)")
    ap.add_argument("--preentrenar", type=Path, default=None, help="carpeta externa con _recortes/ (dataset.externos)")
    ap.add_argument("--epocas-pre", type=int, default=3)
    ap.add_argument("--epocas-cabeza", type=int, default=15)
    ap.add_argument("--epocas-ajuste", type=int, default=10)
    ap.add_argument("--epocas-qat", type=int, default=4)
    ap.add_argument("--lote", type=int, default=16)
    ap.add_argument("--sin-pesos", action="store_true", help="sin pesos de ImageNet (sin internet): solo prueba")
    a = ap.parse_args()
    datos_dir = a.salida or (PROCESADO_SINTETICO if a.sintetico else PROCESADO)

    m = preparar(datos_dir)
    por_clase = m.groupby("clase")["sitio"].nunique().reindex(CLASES, fill_value=0)
    pocas = por_clase[por_clase < MIN_SITIOS_POR_CLASE]
    if len(pocas):
        sys.exit(f"Faltan sitios etiquetados (mínimo {MIN_SITIOS_POR_CLASE} por clase): "
                 + ", ".join(f"{c} = {n}" for c, n in pocas.items()))
    m["split"] = dividir(m).to_numpy()
    sint = "SINTETICO" if a.sintetico or m["notas"].str.contains("SINTETICO").any() else ""
    aviso = " — SINTÉTICO: prueba del flujo, NO es resultado" if sint else ""
    version = (f"{datetime.now(ZONA_LOCAL):%Y%m%d-%H%M}" + (f"-{sint}" if sint else "")
               + ("-PRE" if a.preentrenar else "") + ("-SINPESOS" if a.sin_pesos else ""))
    carpeta = SALIDAS / version
    carpeta.mkdir(parents=True, exist_ok=True)
    m[["id", "clase", "sitio", "split"]].to_csv(carpeta / "division.csv", index=False)
    print(f"Versión {version}\n{m.groupby(['split', 'clase']).size().unstack(0).reindex(CLASES).fillna(0).astype(int)}")

    arqs = list(ARQ) if a.comparar else [a.arquitectura]
    resultados = {arq: correr(arq, m, a, carpeta, aviso) for arq in arqs}

    # Modelo para el celular y el bot: el mejor int8 (F1 macro en test) entre las arquitecturas entrenadas.
    # En la prueba sintética del 5-nov MobileNetV3 perdía mucho en int8 y MobileNetV2 no: se decide con los datos.
    elegida = max(resultados, key=lambda r: resultados[r]["variantes"][mejor_int8(resultados[r])]["f1_macro"])
    var = mejor_int8(resultados[elegida])
    info = {"version": version, "sintetico": bool(sint), "arquitectura": elegida, "variante": var,
            "tflite": f"{elegida}/modelo_{var}.tflite", "entrada_tflite": "uint8 0-255 (foto con relleno a 224x224)",
            "tam": TAM, "clases": CLASES}
    (carpeta / "info.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    (carpeta / "etiquetas.txt").write_text("\n".join(CLASES) + "\n", encoding="utf-8")
    (carpeta / "metricas.json").write_text(json.dumps(resultados, indent=2, ensure_ascii=False, default=float),
                                           encoding="utf-8")
    (SALIDAS / "ultimo.txt").write_text(version, encoding="utf-8")

    n = {s: (int((m["split"] == s).sum()), int(m.loc[m["split"] == s, "sitio"].nunique())) for s in ("train", "val", "test")}
    l = [f"# Modelo de fotos {version}{aviso}", "",
         "División por SITIO: " + ", ".join(f"{s} {f} fotos / {si} sitios" for s, (f, si) in n.items()),
         f"Pesos ImageNet: {'no' if a.sin_pesos else 'sí'} · pre-entrenamiento externo: "
         + (json.dumps(resultados[arqs[0]]['preentrenamiento'], ensure_ascii=False) if a.preentrenar else "no"), "",
         "## float32 vs. int8 PTQ vs. int8 QAT (test por sitio)", "",
         "| Arquitectura | Variante | Exactitud | F1 macro | Tamaño | Latencia en el PC* | Acuerdo con Keras |",
         "|---|---|---|---|---|---|---|"]
    for arq, r in resultados.items():
        l.append(f"| {arq} | Keras float32 | {r['keras']['exactitud']:.3f} | {r['keras']['f1_macro']:.3f} | — | — | — |")
        for k, v in r["variantes"].items():
            l.append(f"| {arq} | {k} | {v['exactitud']:.3f} | {v['f1_macro']:.3f} | {v['tamano_kb']} KB | "
                     f"{v['latencia_ms_pc']} ms | {v['acuerdo_con_keras']:.1%} |")
    l += ["", "*Mediana por foto con el intérprete TFLite en el PC (XNNPACK); NO es la latencia del celular "
          "(esa la mide la página web/clasificador).", ""]
    for arq, r in resultados.items():
        rep = r["por_clase"]
        l += [f"## {arq}: por clase (Keras float32)", "", "| Clase | Precisión | Exhaustividad | F1 | Fotos |",
              "|---|---|---|---|---|"]
        l += [f"| {c} | {rep[c]['precision']:.2f} | {rep[c]['recall']:.2f} | {rep[c]['f1-score']:.2f} | "
              f"{int(rep[c]['support'])} |" for c in CLASES]
        l += ["", f"Figuras: `{arq}/matriz_confusion.png`, `{arq}/errores.png` ({r['errores_mostrados']} errores), "
                  f"`{arq}/gradcam.png`.", ""]
    # R3: pérdida por cuantización CLASE POR CLASE (las clases raras, como tapa u obstáculo, son las que más caen)
    for arq, r in resultados.items():
        vs = list(r["variantes"])
        l += [f"## {arq}: F1 por clase, float32 vs. int8 (test por sitio)", "",
              "| Clase | Fotos test | Keras float32 | " + " | ".join(vs) + " | Peor caída int8 vs. float32 |",
              "|---|---|---|" + "---|" * len(vs) + "---|"]
        for c in CLASES:
            f_float = r["por_clase"][c]["f1-score"]
            f_var = [r["variantes"][v]["f1_por_clase"][c] for v in vs]
            caida = min((x - f_float for v, x in zip(vs, f_var) if v.startswith("int8")), default=0.0)
            l.append(f"| {c} | {int(r['por_clase'][c]['support'])} | {f_float:.2f} | "
                     + " | ".join(f"{x:.2f}" for x in f_var) + f" | {caida:+.2f} |")
        l.append("")
    l.append(f"Modelo para el celular y el bot: `{info['tflite']}` (info.json).")
    (carpeta / "reporte.md").write_text("\n".join(l) + "\n", encoding="utf-8")
    print("\n".join(l))
    print(f"\nTodo en {carpeta}")


if __name__ == "__main__":
    main()
