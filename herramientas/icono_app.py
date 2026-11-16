"""Genera el icono de la app VÍA VIVA (PNG para la app instalable y .ico para el acceso directo de Windows).

Mismo dibujo que el favicon de la web de Dany (web/en_linea/tablero.html): asfalto, dos trazos amarillos de carril y
el punto rojo del hueco. Uso:  viaviva\\.venv\\Scripts\\python -m herramientas.icono_app
"""
from pathlib import Path

from PIL import Image, ImageDraw

SALIDA = Path(__file__).resolve().parents[1] / "viaviva" / "web" / "icono"
ASFALTO, SENAL, PELIGRO = (10, 10, 10), (255, 214, 10), (255, 59, 48)


def dibujar(lado: int, margen: float = 0.0) -> Image.Image:
    """Lienzo de 32 unidades como el SVG original; `margen` deja aire para iconos «maskable»."""
    im = Image.new("RGBA", (lado, lado), ASFALTO + (255,))
    d = ImageDraw.Draw(im)
    u = lado * (1 - 2 * margen) / 32
    o = lado * margen

    def caja(x, y, w, h):
        return [o + x * u, o + y * u, o + (x + w) * u - 1, o + (y + h) * u - 1]

    d.rectangle(caja(14, 4, 4, 7), fill=SENAL)
    d.rectangle(caja(14, 14, 4, 7), fill=SENAL)
    d.ellipse(caja(12.5, 22.5, 7, 7), fill=PELIGRO)
    return im


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    grande = dibujar(1024)
    for lado in (192, 512):
        grande.resize((lado, lado), Image.LANCZOS).save(SALIDA / f"viaviva-{lado}.png", optimize=True)
    dibujar(1024, margen=0.12).resize((512, 512), Image.LANCZOS).save(SALIDA / "viaviva-maskable-512.png",
                                                                      optimize=True)
    grande.resize((180, 180), Image.LANCZOS).save(SALIDA / "apple-touch-icon.png", optimize=True)
    grande.save(SALIDA / "viaviva.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128),
                                               (256, 256)])
    print(f"Iconos en {SALIDA}")


if __name__ == "__main__":
    main()
