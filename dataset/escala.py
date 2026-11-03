"""Escala y perspectiva con la tarjeta ArUco: vista cenital rectificada y área APROXIMADA del daño en cm².

Para cada foto con la tarjeta (docs/tarjeta_aruco.pdf, marcador de 80 mm):
  1. Detecta el marcador (DICT_4X4_50) y sus 4 esquinas con precisión subpíxel.
  2. Homografía de 4 puntos: esquinas en la imagen → cuadrado de 80 × 80 mm en el plano del piso. Con ella la foto
     se "endereza" a vista cenital a escala fija (RES_MM mm por píxel), hasta ±RADIO_MM alrededor de la tarjeta.
  3. Área del daño (huecos, parches y grietas): en la vista rectificada se separa lo OSCURO del asfalto con el umbral
     de Otsu, se quita la tarjeta, se limpia con apertura/cierre y se toma la mancha más grande. Área = píxeles × RES².
     Es aproximada: falla si hay sombras fuertes, agua o si el daño no es más oscuro que el asfalto. Por eso se valida.
  4. Validación (--validar): contra las medidas con regla en campo (largo_regla_cm y ancho_regla_cm del metadatos,
     opcionales): área de referencia = π/4 · largo · ancho (elipse). Con datos sintéticos, además contra el área
     verdadera dibujada (verdad_escala.csv).
La homografía solo vale para el PLANO del piso: lo que sobresale (un cono) o se hunde (el fondo del hueco) sale
deformado; el área medida es la de la boca del daño en el plano de la tarjeta.

Salidas (en la carpeta del dataset): escala.csv, rectificadas/<id>.jpg (con el contorno dibujado) y, con
--validar, validacion_escala.csv.

Uso (desde via-viva/):
  dataset\\.venv\\Scripts\\python -m dataset.escala                  fotos con ángulo cenital (o todas: --todas)
  dataset\\.venv\\Scripts\\python -m dataset.escala --validar
  dataset\\.venv\\Scripts\\python -m dataset.escala --sintetico --validar
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

from dataset.comun import PROCESADO, PROCESADO_SINTETICO, guardar_csv, leer_metadatos
from dataset.tarjeta_aruco import DICCIONARIO, LADO_MARCADOR_MM, LADO_TARJETA_MM

RES_MM = 1.0              # mm por píxel de la vista rectificada
RADIO_MM = 1500           # se rectifica hasta 1,5 m alrededor de la tarjeta
AREA_MIN_CM2 = 20.0       # manchas más chicas se ignoran (ruido, piedras)
CLASES_AREA = {"hueco", "parche", "grieta"}

_DETECTOR = None


def detector():
    global _DETECTOR
    if _DETECTOR is None:
        p = cv2.aruco.DetectorParameters()
        p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        _DETECTOR = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(DICCIONARIO), p)
    return _DETECTOR


def detectar(bgr: np.ndarray) -> list[tuple[int, np.ndarray]]:
    """[(id, esquinas 4×2)] ordenados del marcador más grande al más chico (el más grande se ve mejor)."""
    gris = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    esquinas, ids, _ = detector().detectMarkers(gris)
    if ids is None:
        return []
    m = [(int(i), c.reshape(4, 2)) for i, c in zip(ids.ravel(), esquinas)]
    return sorted(m, key=lambda x: -cv2.contourArea(x[1].astype(np.float32)))


def homografia(esquinas: np.ndarray) -> np.ndarray:
    """Imagen (px) → plano del piso (mm). OpenCV da las esquinas en orden: sup-izq, sup-der, inf-der, inf-izq."""
    L = LADO_MARCADOR_MM
    plano = np.float32([[0, 0], [L, 0], [L, L], [0, L]])
    return cv2.getPerspectiveTransform(esquinas.astype(np.float32), plano)


def rectificar(bgr: np.ndarray, H: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vista cenital a RES_MM mm/px. Devuelve (imagen, máscara de píxeles válidos, homografía imagen→rectificada)."""
    h, w = bgr.shape[:2]
    bordes = cv2.perspectiveTransform(np.float32([[[0, 0]], [[w, 0]], [[w, h]], [[0, h]]]), H).reshape(4, 2)
    c = LADO_MARCADOR_MM / 2
    x0, y0 = np.maximum(bordes.min(0), [c - RADIO_MM, c - RADIO_MM])
    x1, y1 = np.minimum(bordes.max(0), [c + RADIO_MM, c + RADIO_MM])
    T = np.array([[1 / RES_MM, 0, -x0 / RES_MM], [0, 1 / RES_MM, -y0 / RES_MM], [0, 0, 1]])
    Hr = T @ H
    tam = (int(math.ceil((x1 - x0) / RES_MM)), int(math.ceil((y1 - y0) / RES_MM)))
    rect = cv2.warpPerspective(bgr, Hr, tam, flags=cv2.INTER_LINEAR)
    valida = cv2.warpPerspective(np.full((h, w), 255, np.uint8), Hr, tam, flags=cv2.INTER_NEAREST)
    return rect, cv2.erode(valida, np.ones((5, 5), np.uint8)), Hr


def area_dano(rect: np.ndarray, valida: np.ndarray, Hr: np.ndarray, H: np.ndarray) -> dict:
    """Mancha oscura más grande fuera de la tarjeta → área (cm²), largo y ancho (cm) y su contorno."""
    gris = cv2.GaussianBlur(cv2.cvtColor(rect, cv2.COLOR_BGR2GRAY), (0, 0), 3 / RES_MM)
    # La tarjeta completa (marcador + margen blanco) más 5 mm se saca del análisis
    m = (LADO_TARJETA_MM - LADO_MARCADOR_MM) / 2 + 5
    L = LADO_MARCADOR_MM
    tarjeta_mm = np.float32([[[-m, -m]], [[L + m, -m]], [[L + m, L + m]], [[-m, L + m]]])
    T = Hr @ np.linalg.inv(H)                       # plano (mm) → rectificada (px)
    tarjeta = cv2.perspectiveTransform(tarjeta_mm, T).astype(np.int32)
    zona = valida.copy()
    cv2.fillPoly(zona, [tarjeta.reshape(-1, 2)], 0)
    if (zona > 0).sum() < 1000:
        return {}
    valores = gris[zona > 0].reshape(-1, 1)
    umbral, _ = cv2.threshold(valores, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Con charcos o pintura clara, Otsu separa "claro vs. asfalto" y todo el asfalto queda como oscuro.
    # El daño debe ser claramente más oscuro que el asfalto típico (la mediana): a lo sumo el 65 % de ella.
    umbral = min(umbral, 0.65 * float(np.median(valores)))
    oscuro = ((gris < umbral) & (zona > 0)).astype(np.uint8) * 255
    k = max(3, int(round(8 / RES_MM)) | 1)
    oscuro = cv2.morphologyEx(oscuro, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    oscuro = cv2.morphologyEx(oscuro, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    # Las manchas que tocan el borde de la foto se descartan: las sombras duras entran desde afuera, y el protocolo
    # pide el daño COMPLETO dentro de la foto.
    borde = cv2.erode(valida, np.ones((15, 15), np.uint8)) == 0
    n, etiquetas, stats, _ = cv2.connectedComponentsWithStats(oscuro)
    candidatas = [k for k in range(1, n) if not borde[etiquetas == k].any()]
    if not candidatas:
        return {}
    k = max(candidatas, key=lambda j: stats[j, cv2.CC_STAT_AREA])
    contornos, _ = cv2.findContours((etiquetas == k).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cont = max(contornos, key=cv2.contourArea)
    area_cm2 = cv2.contourArea(cont) * RES_MM ** 2 / 100
    if area_cm2 < AREA_MIN_CM2:
        return {}
    (_, _), (a, b), _ = cv2.minAreaRect(cont)
    return {"area_cm2": round(area_cm2, 1), "largo_cm": round(max(a, b) * RES_MM / 10, 1),
            "ancho_cm": round(min(a, b) * RES_MM / 10, 1), "contorno": cont, "tarjeta": tarjeta}


def procesar(ruta: Path, clase: str, dir_rect: Path) -> dict:
    bgr = cv2.imread(str(ruta))
    if bgr is None:
        return {"estado": "no se pudo leer"}
    marcas = detectar(bgr)
    if not marcas:
        return {"estado": "sin tarjeta"}
    id_m, esq = marcas[0]
    lados = [np.linalg.norm(esq[k] - esq[(k + 1) % 4]) for k in range(4)]
    H = homografia(esq)
    rect, valida, Hr = rectificar(bgr, H)
    r = {"estado": "ok", "marcador_id": id_m, "n_marcadores": len(marcas),
         # escala en la foto original (en el plano de la tarjeta; cambia con la distancia si no es cenital)
         "px_por_cm": round(float(np.mean(lados)) / (LADO_MARCADOR_MM / 10), 2),
         "inclinacion": round(float(max(lados) / min(lados)), 3),   # 1 = cenital perfecta
         "area_cm2": "", "largo_cm": "", "ancho_cm": "", "metodo": ""}
    dibujo = rect.copy()
    if clase in CLASES_AREA:
        d = area_dano(rect, valida, Hr, H)
        if d:
            r.update(area_cm2=d["area_cm2"], largo_cm=d["largo_cm"], ancho_cm=d["ancho_cm"], metodo="oscuro_otsu")
            cv2.drawContours(dibujo, [d["contorno"]], -1, (0, 0, 255), 2)
            cv2.polylines(dibujo, [d["tarjeta"].reshape(-1, 2)], True, (0, 200, 0), 2)
        else:
            r["estado"] = "tarjeta ok, sin mancha"
    cv2.putText(dibujo, f"{RES_MM:g} mm/px  area {r['area_cm2'] or '-'} cm2", (10, 25), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (0, 255, 255), 2)
    cv2.imwrite(str(dir_rect / ruta.name), dibujo, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return r


def validar(salida: Path, esc: pd.DataFrame, meta: pd.DataFrame, sintetico: bool) -> pd.DataFrame:
    d = esc.merge(meta[["id", "largo_regla_cm", "ancho_regla_cm"]], on="id")
    d = d[pd.to_numeric(d["area_cm2"], errors="coerce").notna()]
    d["area_cm2"] = d["area_cm2"].astype(float)
    filas = []
    regla = d[(d["largo_regla_cm"] != "") & (d["ancho_regla_cm"] != "")].copy()
    if len(regla):
        regla["area_regla_cm2"] = math.pi / 4 * regla["largo_regla_cm"].astype(float) * regla["ancho_regla_cm"].astype(float)
        regla["error_regla_pct"] = 100 * (regla["area_cm2"] - regla["area_regla_cm2"]) / regla["area_regla_cm2"]
        regla["error_largo_pct"] = 100 * (regla["largo_cm"].astype(float) / regla["largo_regla_cm"].astype(float) - 1)
        filas.append(("regla (elipse π/4·L·A)", regla["error_regla_pct"]))
        filas.append(("largo vs. regla", regla["error_largo_pct"]))
        d = d.merge(regla[["id", "area_regla_cm2", "error_regla_pct", "error_largo_pct"]], on="id", how="left")
    verdad = salida / "verdad_escala.csv"
    if sintetico and verdad.exists():
        v = pd.read_csv(verdad, dtype={"id": str}).dropna(subset=["area_real_cm2"])
        d = d.merge(v[["id", "area_real_cm2"]], on="id", how="left")
        d["error_real_pct"] = 100 * (d["area_cm2"] - d["area_real_cm2"]) / d["area_real_cm2"]
        filas.append(("área verdadera (SINTÉTICO)", d["error_real_pct"].dropna()))
    guardar_csv(d, salida / "validacion_escala.csv")
    print(f"\nValidación del área{' — SINTÉTICO' if sintetico else ''} ({len(d)} fotos con área calculada)")
    if not filas:
        print("  No hay medidas con regla (largo_regla_cm / ancho_regla_cm) para comparar.")
    for nombre, e in filas:
        e = e.dropna()
        if len(e):
            print(f"  contra {nombre}: n = {len(e)}, error medio = {e.mean():+.1f} %, "
                  f"error absoluto medio = {e.abs().mean():.1f} %, mediana |e| = {e.abs().median():.1f} %")
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, default=None)
    ap.add_argument("--sintetico", action="store_true")
    ap.add_argument("--todas", action="store_true", help="buscar la tarjeta en todas las fotos, no solo las cenitales")
    ap.add_argument("--validar", action="store_true")
    a = ap.parse_args()
    salida = a.salida or (PROCESADO_SINTETICO if a.sintetico else PROCESADO)
    meta = leer_metadatos(salida / "metadatos.csv")
    if meta.empty:
        raise SystemExit(f"No hay {salida / 'metadatos.csv'}: correr primero dataset.ingesta")
    fotos = meta if a.todas else meta[meta["angulo"] == "cenital"]
    if fotos.empty:
        raise SystemExit("No hay fotos con ángulo 'cenital' etiquetadas (usar --todas para buscar en todas)")
    dir_rect = salida / "rectificadas"
    dir_rect.mkdir(exist_ok=True)
    filas = []
    for _, f in fotos.iterrows():
        filas.append({"id": f["id"], **procesar(salida / f["archivo"], f["clase"], dir_rect)})
    esc = pd.DataFrame(filas)
    guardar_csv(esc, salida / "escala.csv")
    print(f"{len(esc)} fotos revisadas: " + ", ".join(f"{k} = {v}" for k, v in esc["estado"].value_counts().items()))
    print(f"Escrito {salida / 'escala.csv'} y las vistas rectificadas en {dir_rect}")
    if a.validar:
        validar(salida, esc, meta, a.sintetico)


if __name__ == "__main__":
    main()
