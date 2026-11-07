"""Datasets externos de baches (docs/datasets_externos.md): descargar, revisar y preparar recortes para pre-entrenar.

  --descargar-kaggle     baja andrewmvd/pothole-detection (DbCL v1.0) a data/externo/kaggle_potholes
                         (necesita C:\\Users\\<usuario>\\.kaggle\\kaggle.json y `pip install kaggle`)
  --revisar CARPETA      imágenes, recuadros PASCAL VOC (.xml) o YOLO (.txt), tamaños, duplicados (dHash) y posible
                         fuga con nuestras fotos (data/raw/fotos, data/procesado/fotos) → CARPETA/_revision.md
  --recortes CARPETA     recortes 'hueco' (recuadro + 20 %) y 'no_hueco' (parche del mismo tamaño que no toca ningún
                         recuadro) → CARPETA/_recortes/{hueco,no_hueco}/ para el pre-entrenamiento de dataset.modelo
  --sintetico-voc        genera data/externo/SINTETICO_voc (VOC falso con huecos dibujados) SOLO para probar el flujo

Las imágenes externas nunca entran a data/procesado ni a la evaluación: esa es siempre con nuestras fotos.
"""
from __future__ import annotations

import argparse
import random
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from pathlib import PurePosixPath

import cv2
import numpy as np

from dataset.comun import DATA, DHASH_CASI_IGUAL, PROCESADO, CRUDAS

EXTERNO = DATA / "externo"
EXT_IMG = {".jpg", ".jpeg", ".png", ".bmp"}


def recuadros(img_path: Path, ancho: int, alto: int) -> list[tuple[int, int, int, int]]:
    """[(x0, y0, x1, y1)] en píxeles desde el .xml VOC o el .txt YOLO con el mismo nombre (en la carpeta o en annotations/)."""
    candidatos = [img_path.with_suffix(".xml"), img_path.parent.parent / "annotations" / f"{img_path.stem}.xml",
                  img_path.with_suffix(".txt"), img_path.parent.parent / "labels" / f"{img_path.stem}.txt"]
    for c in candidatos:
        if not c.exists():
            continue
        if c.suffix == ".xml":
            r = ET.parse(c).getroot()
            return [tuple(int(float(o.find("bndbox").find(k).text)) for k in ("xmin", "ymin", "xmax", "ymax"))
                    for o in r.iter("object")]
        cajas = []
        for linea in c.read_text().split("\n"):
            p = linea.split()
            if len(p) == 5:
                cx, cy, w, h = (float(v) for v in p[1:])
                cajas.append((int((cx - w / 2) * ancho), int((cy - h / 2) * alto), int((cx + w / 2) * ancho),
                              int((cy + h / 2) * alto)))
        return cajas
    return []


def imagenes(carpeta: Path) -> list[Path]:
    return sorted(p for p in carpeta.rglob("*") if p.suffix.lower() in EXT_IMG and "_recortes" not in p.parts)


def dhash(img) -> int:
    g = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (9, 8), interpolation=cv2.INTER_AREA)
    return int("".join("1" if b else "0" for b in (g[:, 1:] > g[:, :-1]).flatten()), 2)


def revisar(carpeta: Path) -> str:
    fotos = imagenes(carpeta)
    tam, cajas, sin, hashes = [], [], 0, {}
    for p in fotos:
        img = cv2.imread(str(p))
        if img is None:
            continue
        h, w = img.shape[:2]
        tam.append((w, h))
        c = recuadros(p, w, h)
        sin += not c
        cajas += [((x1 - x0) * (y1 - y0)) / (w * h) for x0, y0, x1, y1 in c]
        hashes[p] = dhash(img)
    lista = list(hashes.items())
    dup = sum(any(bin(a ^ b).count("1") <= DHASH_CASI_IGUAL for _, b in lista[:i]) for i, (_, a) in enumerate(lista))
    nuestras = [p for d in (CRUDAS, PROCESADO / "fotos") if d.exists() for p in d.rglob("*.jpg")]
    fuga = 0
    for p in nuestras:
        img = cv2.imread(str(p))
        if img is not None:
            h0 = dhash(img)
            fuga += any(bin(h0 ^ b).count("1") <= DHASH_CASI_IGUAL for b in hashes.values())
    w = np.array(tam) if tam else np.zeros((0, 2))
    l = [f"# Revisión de {carpeta.name}", "",
         f"- Imágenes legibles: **{len(tam)}** de {len(fotos)}",
         f"- Tamaño (ancho × alto): mediana {int(np.median(w[:, 0])) if len(w) else 0} × "
         f"{int(np.median(w[:, 1])) if len(w) else 0} px; mínimo {int(w[:, 0].min()) if len(w) else 0} px de ancho",
         f"- Recuadros: **{len(cajas)}** ({len(cajas) / max(1, len(tam)):.2f} por imagen); imágenes sin recuadro: {sin}",
         f"- Área del recuadro / imagen: mediana {np.median(cajas) if cajas else 0:.3f}",
         f"- Casi duplicadas dentro del dataset (dHash ≤ {DHASH_CASI_IGUAL}): **{dup}**",
         f"- Posible fuga con nuestras fotos ({len(nuestras)} revisadas): **{fuga}**"]
    texto = "\n".join(l) + "\n"
    (carpeta / "_revision.md").write_text(texto, encoding="utf-8")
    return texto


def recortes(carpeta: Path, lado: int = 224, semilla: int = 0) -> tuple[int, int]:
    """Recortes positivos y negativos para la tarea auxiliar hueco / no_hueco."""
    rnd = random.Random(semilla)
    sal = carpeta / "_recortes"
    for c in ("hueco", "no_hueco"):
        (sal / c).mkdir(parents=True, exist_ok=True)
    n_pos = n_neg = 0
    for p in imagenes(carpeta):
        img = cv2.imread(str(p))
        if img is None:
            continue
        h, w = img.shape[:2]
        cajas = recuadros(p, w, h)
        for k, (x0, y0, x1, y1) in enumerate(cajas):
            mx, my = int(0.2 * (x1 - x0)), int(0.2 * (y1 - y0))
            r = img[max(0, y0 - my):min(h, y1 + my), max(0, x0 - mx):min(w, x1 + mx)]
            if r.size and min(r.shape[:2]) >= 16:
                cv2.imwrite(str(sal / "hueco" / f"{p.stem}_{k}.jpg"), cv2.resize(r, (lado, lado)))
                n_pos += 1
        if not cajas:
            continue
        lado_n = int(np.median([max(x1 - x0, y1 - y0) for x0, y0, x1, y1 in cajas]) * 1.4)
        lado_n = max(32, min(lado_n, w - 1, h - 1))
        for _ in range(30):                          # busca un parche que no toque ningún recuadro
            x, y = rnd.randint(0, w - lado_n), rnd.randint(0, h - lado_n)
            if all(x + lado_n < a or x > c or y + lado_n < b or y > d for a, b, c, d in cajas):
                cv2.imwrite(str(sal / "no_hueco" / f"{p.stem}.jpg"), cv2.resize(img[y:y + lado_n, x:x + lado_n], (lado, lado)))
                n_neg += 1
                break
    return n_pos, n_neg


def sintetico_voc(n: int = 120, semilla: int = 3) -> Path:
    """VOC falso para probar el flujo: asfalto con 1-2 huecos dibujados y sus recuadros. SINTÉTICO."""
    from dataset.sintetico import ALTO, ANCHO, asfalto, poligono_irregular
    rng = np.random.default_rng(semilla)
    raiz = EXTERNO / "SINTETICO_voc"
    (raiz / "images").mkdir(parents=True, exist_ok=True)
    (raiz / "annotations").mkdir(parents=True, exist_ok=True)
    for i in range(n):
        img = asfalto(rng)
        objs = []
        for _ in range(int(rng.integers(1, 3))):
            cx, cy = rng.uniform(0.25, 0.75) * ANCHO, rng.uniform(0.25, 0.75) * ALTO
            poli = poligono_irregular(rng, cx, cy, rng.uniform(25, 60))
            cv2.fillPoly(img, [poli], (rng.uniform(20, 45),) * 3)
            x, y, w, h = cv2.boundingRect(poli)
            objs.append(f"<object><name>pothole</name><bndbox><xmin>{x}</xmin><ymin>{y}</ymin><xmax>{x + w}</xmax>"
                        f"<ymax>{y + h}</ymax></bndbox></object>")
        cv2.imwrite(str(raiz / "images" / f"s{i:04d}.png"), np.clip(img, 0, 255).astype(np.uint8))
        (raiz / "annotations" / f"s{i:04d}.xml").write_text(
            f"<annotation><filename>s{i:04d}.png</filename>{''.join(objs)}</annotation>", encoding="utf-8")
    return raiz


def extraer_zip_seguro(archivo: Path, destino: Path) -> None:
    """Extrae un ZIP solo dentro de destino y rechaza rutas o enlaces peligrosos."""
    raiz = destino.resolve()
    with zipfile.ZipFile(archivo) as z:
        miembros = []
        for info in z.infolist():
            # ZIP define rutas con '/', pero algunos archivos maliciosos usan '\\'.
            nombre = info.filename.replace("\\", "/")
            ruta = PurePosixPath(nombre)
            if (not nombre or not ruta.parts or ruta.is_absolute() or ".." in ruta.parts
                    or re.match(r"^[A-Za-z]:", nombre)):
                raise ValueError(f"Ruta insegura dentro del ZIP: {info.filename!r}")
            modo = (info.external_attr >> 16) & 0o170000
            if modo == 0o120000:
                raise ValueError(f"No se permiten enlaces simbólicos en el ZIP: {info.filename!r}")
            salida = (raiz / Path(*ruta.parts)).resolve()
            try:
                salida.relative_to(raiz)
            except ValueError as exc:
                raise ValueError(f"La ruta escapa de la carpeta de destino: {info.filename!r}") from exc
            miembros.append((info, salida))

        # Validar todos los nombres antes de escribir el primer archivo.
        for info, salida in miembros:
            if info.is_dir():
                salida.mkdir(parents=True, exist_ok=True)
                continue
            salida.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as origen, salida.open("wb") as archivo_salida:
                shutil.copyfileobj(origen, archivo_salida)


def descargar_kaggle() -> Path:
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except ImportError:
        sys.exit("Falta el paquete: dataset\\.venv\\Scripts\\python -m pip install kaggle")
    api = KaggleApi()
    api.authenticate()                              # lee ~/.kaggle/kaggle.json (nunca se copia al repo)
    destino = EXTERNO / "kaggle_potholes"
    destino.mkdir(parents=True, exist_ok=True)
    api.dataset_download_files("andrewmvd/pothole-detection", path=str(destino), quiet=False)
    for z in destino.glob("*.zip"):
        extraer_zip_seguro(z, destino)
        z.unlink()
    return destino


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--descargar-kaggle", action="store_true")
    ap.add_argument("--revisar", type=Path)
    ap.add_argument("--recortes", type=Path)
    ap.add_argument("--sintetico-voc", action="store_true")
    a = ap.parse_args()
    if a.descargar_kaggle:
        print(f"Descargado en {descargar_kaggle()}")
    if a.sintetico_voc:
        print(f"VOC SINTÉTICO en {sintetico_voc()}")
    if a.revisar:
        print(revisar(a.revisar))
    if a.recortes:
        pos, neg = recortes(a.recortes)
        print(f"Recortes en {a.recortes / '_recortes'}: {pos} hueco, {neg} no_hueco")


if __name__ == "__main__":
    main()
