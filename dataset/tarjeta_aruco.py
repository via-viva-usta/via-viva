"""Genera docs/tarjeta_aruco.pdf: 4 tarjetas ArUco de 10 × 10 cm por hoja carta, con regla para verificar la escala.

Cada tarjeta: marcador ArUco DICT_4X4_50 (ids 0-3) de LADO_MARCADOR_MM = 80 mm (borde negro a borde negro) centrado
en un cuadro blanco de 100 × 100 mm (10 mm de margen blanco, necesario para que el detector encuentre el borde).
dataset/escala.py usa ESTE lado (80 mm) para la homografía: si se cambia aquí, cambia allá (se importa de aquí).

El marcador se dibuja como rectángulos vectoriales (no como imagen) para que la impresora no lo suavice.

Uso (desde via-viva/):  dataset\\.venv\\Scripts\\python -m dataset.tarjeta_aruco
Imprimir al 100 % ("tamaño real", NUNCA "ajustar a la página") y medir la regla: debe dar 200 mm exactos.
"""
from __future__ import annotations

import argparse

import cv2
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from dataset.comun import RAIZ

DICCIONARIO = cv2.aruco.DICT_4X4_50
LADO_MARCADOR_MM = 80.0
LADO_TARJETA_MM = 100.0
IDS = [0, 1, 2, 3]


def bits_marcador(id_: int) -> list[list[int]]:
    """Matriz 6 × 6 (borde negro de 1 módulo + 4 × 4 de datos): 1 = blanco, 0 = negro."""
    d = cv2.aruco.getPredefinedDictionary(DICCIONARIO)
    img = cv2.aruco.generateImageMarker(d, id_, 6)       # 6 px = 1 px por módulo
    return [[1 if img[f, c] > 127 else 0 for c in range(6)] for f in range(6)]


def tarjeta(c: canvas.Canvas, x0: float, y0: float, id_: int) -> None:
    """Dibuja una tarjeta con su esquina inferior izquierda en (x0, y0), en puntos."""
    lado = LADO_TARJETA_MM * mm
    c.setLineWidth(0.3)
    c.setStrokeGray(0.6)
    c.setDash(2, 2)
    c.rect(x0, y0, lado, lado, stroke=1, fill=0)          # línea de corte
    c.setDash()
    modulo = LADO_MARCADOR_MM * mm / 6
    mx = x0 + (lado - 6 * modulo) / 2
    my = y0 + (lado - 6 * modulo) / 2
    c.setFillGray(0)
    for f, fila in enumerate(bits_marcador(id_)):
        for k, b in enumerate(fila):
            if b == 0:   # la fila 0 es la de arriba; en PDF y crece hacia arriba
                c.rect(mx + k * modulo, my + (5 - f) * modulo, modulo, modulo, stroke=0, fill=1)
    c.setFont("Helvetica", 5.5)
    c.setFillGray(0.35)
    c.drawCentredString(x0 + lado / 2, y0 + 2.2 * mm,
                        f"VIA VIVA · ArUco 4x4_50 id {id_} · lado negro = {LADO_MARCADOR_MM:.0f} mm · no doblar")


def regla(c: canvas.Canvas, x0: float, y0: float, largo_mm: int = 200) -> None:
    c.setStrokeGray(0)
    c.setLineWidth(0.5)
    c.line(x0, y0, x0 + largo_mm * mm, y0)
    for k in range(largo_mm + 1):
        alto = 5 if k % 10 == 0 else (3.5 if k % 5 == 0 else 2)
        c.line(x0 + k * mm, y0, x0 + k * mm, y0 + alto * mm)
        if k % 10 == 0:
            c.setFont("Helvetica", 6)
            c.setFillGray(0)
            c.drawCentredString(x0 + k * mm, y0 + 6 * mm, str(k // 10))
    c.setFont("Helvetica", 6)
    c.drawString(x0 + largo_mm * mm + 1.5 * mm, y0 + 6 * mm, "cm")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", default=str(RAIZ / "docs" / "tarjeta_aruco.pdf"))
    a = ap.parse_args()

    ancho, alto = letter                                   # 215,9 × 279,4 mm
    c = canvas.Canvas(a.salida, pagesize=letter)
    c.setTitle("VÍA VIVA - tarjetas ArUco de referencia (10 x 10 cm)")
    c.setAuthor("VÍA VIVA - USTA Tunja")
    lado = LADO_TARJETA_MM * mm
    x0 = (ancho - 2 * lado) / 2                            # 7,95 mm de margen lateral
    y_arriba = alto - 9 * mm - lado
    for i, id_ in enumerate(IDS):
        fila, col = divmod(i, 2)
        tarjeta(c, x0 + col * lado, y_arriba - fila * lado, id_)

    y = y_arriba - lado - 14 * mm
    regla(c, x0, y)
    c.setFont("Helvetica-Bold", 8)
    c.setFillGray(0)
    c.drawString(x0, y - 7 * mm, "VERIFICAR ANTES DE USAR: imprimir al 100 % (tamaño real, sin 'ajustar a la página').")
    c.setFont("Helvetica", 7.5)
    lineas = [
        "1. Medir esta regla con una regla de verdad: de 0 a 20 debe dar 200 mm (± 1 mm). Si no, la impresora escaló: reimprimir.",
        f"2. Medir el lado del cuadro negro de cada marcador: {LADO_MARCADOR_MM:.0f} mm. Anotar en la hoja si da distinto.",
        "3. Recortar por la línea punteada; pegar sobre cartón o plastificar (plana, sin brillo). No doblar ni arrugar.",
        "4. En la foto cenital: tarjeta en el piso, junto al daño (no encima), completa en la foto, sin sombra fuerte encima.",
    ]
    for k, t in enumerate(lineas):
        c.drawString(x0, y - (12 + 4.2 * k) * mm, t)
    c.showPage()
    c.save()
    print(f"Escrito {a.salida}: {len(IDS)} tarjetas de {LADO_TARJETA_MM:.0f} mm, marcador de {LADO_MARCADOR_MM:.0f} mm")


if __name__ == "__main__":
    main()
