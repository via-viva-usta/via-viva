"""Fotos SINTÉTICAS para probar el flujo del dataset mientras no haya fotos reales. NUNCA son resultados.

Dibuja asfalto con ruido y, encima, una figura simple por clase (hueco = mancha oscura irregular, resalto = franja
amarilla y negra, grieta = líneas finas, parche = polígono liso, tapa = círculo con rejilla, obstáculo = cono
naranja, línea de carril, cebra, vía buena = nada). Cada "sitio" tiene 4 fotos (contexto, frente, lado, cenital) en el
mismo punto GPS; la cenital lleva la tarjeta ArUco de 80 mm y una leve perspectiva, y se guarda el área VERDADERA del
daño para validar dataset/escala.py. Las fotos llevan EXIF con fecha, hora (-05:00) y GPS, como las del celular.

Salida: data/raw/fotos_sintetico/AAAA-MM-DD_sintetico/*.jpg  y  data/raw/fotos_sintetico/_verdad.csv
Con --etiquetar copia las etiquetas verdaderas a data/procesado_sintetico/metadatos.csv (después de la ingesta).

Uso (desde via-viva/):
  dataset\\.venv\\Scripts\\python -m dataset.sintetico                 genera las fotos
  dataset\\.venv\\Scripts\\python -m dataset.ingesta --sintetico       ingesta normal sobre ellas
  dataset\\.venv\\Scripts\\python -m dataset.sintetico --etiquetar     pone las etiquetas verdaderas
"""
from __future__ import annotations

import argparse
import math
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from PIL import Image

from dataset.comun import (ANGULOS, CLASES, CLASES_DANO, COLUMNAS, CRUDAS_SINTETICO, DATA, LUCES,
                           PROCESADO_SINTETICO, TUNJA, guardar_csv, leer_metadatos)
from dataset.tarjeta_aruco import DICCIONARIO, LADO_MARCADOR_MM

ANCHO, ALTO = 640, 480


def asfalto(rng) -> np.ndarray:
    base = rng.uniform(85, 130)
    ruido = rng.normal(0, 18, (ALTO, ANCHO)).astype(np.float32)
    ruido = cv2.GaussianBlur(ruido, (0, 0), rng.uniform(0.6, 1.4)) + rng.normal(0, 6, (ALTO, ANCHO))
    g = np.clip(base + ruido, 0, 255)
    img = np.dstack([g, g, g * rng.uniform(0.97, 1.03)]).astype(np.float32)
    # piedritas claras del agregado
    for _ in range(rng.integers(150, 400)):
        x, y = rng.integers(0, ANCHO), rng.integers(0, ALTO)
        cv2.circle(img, (int(x), int(y)), int(rng.integers(1, 3)), (base + 50,) * 3, -1)
    return img


def poligono_irregular(rng, cx, cy, r, n=14, rugosidad=0.35) -> np.ndarray:
    ang = np.sort(rng.uniform(0, 2 * np.pi, n))
    rad = r * (1 + rugosidad * rng.uniform(-1, 1, n))
    elong = rng.uniform(0.6, 1.0)
    return np.stack([cx + rad * np.cos(ang), cy + elong * rad * np.sin(ang)], 1).astype(np.int32)


def dibujar(img, clase, rng, escala: float, severidad: str) -> np.ndarray | None:
    """Dibuja la clase. escala = tamaño relativo (1 = cenital, cerca). Devuelve el polígono del daño si aplica."""
    cx, cy = ANCHO * rng.uniform(0.45, 0.65), ALTO * rng.uniform(0.45, 0.6)
    tam = {"leve": 0.6, "media": 1.0, "alta": 1.5}.get(severidad, 1.0)
    poli = None
    if clase == "hueco":
        poli = poligono_irregular(rng, cx, cy, 55 * escala * tam)
        cv2.fillPoly(img, [poli], (rng.uniform(25, 45),) * 3)
        cv2.polylines(img, [poli], True, (150,) * 3, 2)
        interior = poligono_irregular(rng, cx, cy, 30 * escala * tam)
        cv2.fillPoly(img, [interior], (rng.uniform(15, 25),) * 3)
    elif clase == "resalto":
        alto = int(45 * escala)
        y0 = int(cy - alto / 2)
        for x in range(-alto, ANCHO, alto):
            col = (40, 200, 230) if (x // alto) % 2 == 0 else (25, 25, 25)
            pts = np.array([[x, y0], [x + alto, y0], [x + 2 * alto, y0 + alto], [x + alto, y0 + alto]], np.int32)
            cv2.fillPoly(img, [pts], col)
    elif clase == "grieta":
        for _ in range(rng.integers(2, 5)):
            p = np.array([cx + rng.uniform(-80, 80), cy + rng.uniform(-60, 60)])
            d = rng.uniform(0, 2 * np.pi)
            for _ in range(int(40 * escala * tam)):
                d += rng.normal(0, 0.35)
                q = p + 5 * np.array([np.cos(d), np.sin(d)])
                cv2.line(img, tuple(p.astype(int)), tuple(q.astype(int)), (30,) * 3, int(rng.integers(1, 3)))
                p = q
    elif clase == "parche":
        w, h = 120 * escala * tam, 80 * escala * tam
        poli = cv2.boxPoints(((cx, cy), (w, h), rng.uniform(-20, 20))).astype(np.int32)
        cv2.fillPoly(img, [poli], (rng.uniform(45, 70),) * 3)
    elif clase == "tapa":
        r = int(50 * escala)
        cv2.circle(img, (int(cx), int(cy)), r, (95, 100, 105), -1)
        cv2.circle(img, (int(cx), int(cy)), r, (60, 60, 60), 3)
        for k in range(-r, r, max(6, r // 5)):
            cv2.line(img, (int(cx + k), int(cy - r)), (int(cx + k), int(cy + r)), (70, 70, 70), 2)
    elif clase == "obstaculo":
        h = 120 * escala
        pts = np.array([[cx, cy - h / 2], [cx - h / 3, cy + h / 2], [cx + h / 3, cy + h / 2]], np.int32)
        cv2.fillPoly(img, [pts], (20, 110, 240))
        cv2.line(img, (int(cx - h / 6), int(cy)), (int(cx + h / 6), int(cy)), (240, 240, 240), max(3, int(10 * escala)))
    elif clase == "linea_carril":
        col = (240, 240, 240) if rng.random() < 0.5 else (30, 200, 230)
        x = cx + rng.uniform(-60, 60)
        inc = rng.uniform(-0.4, 0.4)
        cv2.line(img, (int(x - inc * ALTO), -10), (int(x + inc * ALTO), ALTO + 10), col, max(4, int(14 * escala)))
    elif clase == "paso_peatonal":
        ancho = int(30 * escala)
        for k in range(-3, 4):
            x = int(cx + k * 2 * ancho)
            cv2.rectangle(img, (x, 0), (x + ancho, ALTO), (235, 235, 235), -1)
    return poli


def pegar_aruco(img, rng, px_por_cm: float, id_: int) -> tuple[np.ndarray, np.ndarray]:
    """Pega la tarjeta (marcador de 80 mm + margen blanco de 10 mm) en el plano del piso, lejos del centro."""
    lado = int(round(LADO_MARCADOR_MM / 10 * px_por_cm))
    marg = int(round(px_por_cm))
    m = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(DICCIONARIO), id_, lado)
    x0, y0 = int(rng.uniform(70, 120)), int(rng.uniform(60, 100))   # lejos del borde: la perspectiva no la corta
    cv2.rectangle(img, (x0, y0), (x0 + lado + 2 * marg, y0 + lado + 2 * marg), (245, 245, 245), -1)
    img[y0 + marg:y0 + marg + lado, x0 + marg:x0 + marg + lado] = np.dstack([m] * 3)
    return img, np.array([x0, y0, lado + 2 * marg])


def luz_y_clima(img, luz: str, mojada: bool, rng) -> np.ndarray:
    if luz == "sol":
        img = img * 1.25 + 10
        pts = np.array([[0, 0], [rng.uniform(100, 300), 0], [rng.uniform(0, 200), ALTO], [0, ALTO]], np.int32)
        sombra = np.ones_like(img)
        cv2.fillPoly(sombra, [pts], (0.6, 0.6, 0.6))
        img = img * sombra
    elif luz == "sombra":
        img = img * 0.75
    elif luz == "nublado":
        img = img * 0.95 + 8
    else:                                       # noche: oscura, azulada, con ruido de sensor y un foco
        img = img * 0.28
        img[..., 0] *= 1.25
        yy, xx = np.mgrid[0:ALTO, 0:ANCHO]
        foco = np.exp(-(((xx - ANCHO / 2) / 260) ** 2 + ((yy - ALTO * 0.8) / 200) ** 2))
        img = img * (1 + 1.6 * foco[..., None]) + rng.normal(0, 7, img.shape)
    if mojada:
        img = img * 0.8
        for _ in range(rng.integers(3, 8)):
            cv2.ellipse(img, (int(rng.uniform(0, ANCHO)), int(rng.uniform(0, ALTO))),
                        (int(rng.uniform(20, 80)), int(rng.uniform(5, 20))), 0, 0, 360, (200, 200, 200), -1)
        img = cv2.GaussianBlur(img, (0, 0), 0.8)
    return np.clip(img, 0, 255)


def perspectiva_leve(img, rng):
    d = 0.06
    src = np.float32([[0, 0], [ANCHO, 0], [ANCHO, ALTO], [0, ALTO]])
    dst = src + np.float32(rng.uniform(-d, d, (4, 2)) * [ANCHO, ALTO])
    H = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, H, (ANCHO, ALTO), borderMode=cv2.BORDER_REFLECT), H


def guardar_con_exif(bgr: np.ndarray, ruta: Path, t: datetime, lat: float, lon: float) -> None:
    img = Image.fromarray(cv2.cvtColor(bgr.astype(np.uint8), cv2.COLOR_BGR2RGB))
    ex = Image.Exif()
    ex[0x0110] = "VIA VIVA sintetico"             # Model
    ex[0x0132] = t.strftime("%Y:%m:%d %H:%M:%S")
    sub = ex.get_ifd(0x8769)
    sub[36867] = t.strftime("%Y:%m:%d %H:%M:%S")
    sub[36881] = "-05:00"

    def dms(v):
        v = abs(v)
        g = int(v)
        m = int((v - g) * 60)
        return (float(g), float(m), round(((v - g) * 60 - m) * 60, 4))

    gps = ex.get_ifd(0x8825)
    gps[1], gps[2] = ("N" if lat >= 0 else "S"), dms(lat)
    gps[3], gps[4] = ("E" if lon >= 0 else "W"), dms(lon)
    img.save(ruta, quality=92, exif=ex)


def puntos_de_calle(n: int, rng) -> list[tuple[float, float]]:
    """Centros de tramos reales de la base (para que la ingesta asigne tramo y barrio); si no hay base, al azar."""
    ruta = DATA / "via_viva.db"
    if ruta.exists():
        con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
        t = pd.read_sql("SELECT lat_centro, lon_centro FROM tramos WHERE barrio NOT LIKE 'Vereda%'", con)
        con.close()
        idx = rng.choice(len(t), n, replace=False)
        return list(zip(t["lat_centro"].iloc[idx], t["lon_centro"].iloc[idx]))
    return [(TUNJA[0] + rng.uniform(-0.02, 0.02), TUNJA[1] + rng.uniform(-0.015, 0.015)) for _ in range(n)]


def generar(sitios_por_clase: int, semilla: int) -> None:
    rng = np.random.default_rng(semilla)
    CRUDAS_SINTETICO.mkdir(parents=True, exist_ok=True)
    puntos = puntos_de_calle(sitios_por_clase * len(CLASES), rng)
    verdad, k = [], 0
    for clase in CLASES:
        for s in range(sitios_por_clase):
            lat, lon = puntos[k]
            k += 1
            t0 = datetime(2026, 10, 5) + timedelta(days=int(rng.integers(0, 28)), hours=int(rng.integers(5, 22)),
                                                   minutes=int(rng.integers(0, 60)))
            luz = LUCES[3] if t0.hour >= 18 or t0.hour < 6 else str(rng.choice(LUCES[:3]))
            mojada = bool(rng.random() < 0.25)
            sev = str(rng.choice(["leve", "media", "alta"])) if clase in CLASES_DANO else ""
            carpeta = CRUDAS_SINTETICO / f"{t0:%Y-%m-%d}_sintetico"
            carpeta.mkdir(exist_ok=True)
            for j, angulo in enumerate(ANGULOS):
                escala = {"contexto": 0.45, "frente": 0.8, "lado": 0.8, "cenital": 1.0}[angulo]
                img = asfalto(rng)
                poli = dibujar(img, clase, rng, escala, sev)
                fila = {"clase": clase, "severidad": sev, "angulo": angulo, "luz": luz,
                        "superficie_mojada": "si" if mojada else "no", "area_real_cm2": "", "px_por_cm": "",
                        "largo_regla_cm": "", "ancho_regla_cm": ""}
                if angulo == "cenital":
                    px_cm = float(rng.uniform(4.0, 6.0))
                    img, _ = pegar_aruco(img, rng, px_cm, int(rng.integers(0, 4)))
                    if poli is not None:
                        (_, _), (w, h), _ = cv2.minAreaRect(poli)
                        fila.update(area_real_cm2=round(cv2.contourArea(poli) / px_cm ** 2, 1),
                                    px_por_cm=round(px_cm, 3), largo_regla_cm=round(max(w, h) / px_cm, 1),
                                    ancho_regla_cm=round(min(w, h) / px_cm, 1))
                img = luz_y_clima(img, luz, mojada, rng)
                if angulo == "cenital":
                    img, _ = perspectiva_leve(img, rng)
                t = t0 + timedelta(seconds=25 * j)
                nombre = f"IMG_{t:%Y%m%d_%H%M%S}_{clase}_{s:02d}_{angulo}.jpg"
                guardar_con_exif(img, carpeta / nombre, t, lat + rng.normal(0, 2e-5), lon + rng.normal(0, 2e-5))
                verdad.append({"origen": f"{carpeta.name}/{nombre}", **fila})
    pd.DataFrame(verdad).to_csv(CRUDAS_SINTETICO / "_verdad.csv", index=False)
    print(f"{len(verdad)} fotos SINTÉTICAS en {CRUDAS_SINTETICO} ({sitios_por_clase} sitios × {len(CLASES)} clases × 4)")


def etiquetar() -> None:
    meta = leer_metadatos(PROCESADO_SINTETICO / "metadatos.csv")
    cal = pd.read_csv(PROCESADO_SINTETICO / "calidad.csv", dtype=str, keep_default_na=False)
    v = pd.read_csv(CRUDAS_SINTETICO / "_verdad.csv", dtype=str, keep_default_na=False)
    v = v.merge(cal[["id", "origen"]], on="origen").set_index("id")
    for col in ["clase", "severidad", "angulo", "luz", "superficie_mojada", "largo_regla_cm", "ancho_regla_cm"]:
        meta[col] = meta["id"].map(v[col]).fillna(meta[col])
    guardar_csv(meta[COLUMNAS], PROCESADO_SINTETICO / "metadatos.csv")
    v[["area_real_cm2", "px_por_cm"]].to_csv(PROCESADO_SINTETICO / "verdad_escala.csv")
    print(f"Etiquetas verdaderas puestas en {len(v)} fotos SINTÉTICAS")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sitios-por-clase", type=int, default=12)
    ap.add_argument("--semilla", type=int, default=7)
    ap.add_argument("--etiquetar", action="store_true")
    a = ap.parse_args()
    etiquetar() if a.etiquetar else generar(a.sitios_por_clase, a.semilla)


if __name__ == "__main__":
    main()
