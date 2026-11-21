"""Espectro de un export de phyphox: PSD, frecuencia con el 95 % de la energía y fs mínima recomendada.

    python -m analysis.espectro <export de phyphox (.csv, carpeta o .zip)> [--salida carpeta] [--fraccion 0.95]

Para cada señal (eje vertical sin gravedad, magnitud y ejes x, y, z) calcula la PSD de Welch sobre la señal remuestreada
a la tasa nativa del teléfono, la frecuencia f_E bajo la cual queda la fracción pedida de la energía, la fs mínima por
Nyquist (2 × f_E) y la recomendada con margen para el filtro antialias (2,5 × f_E). Si f_E queda cerca de la mitad de
la tasa nativa, el teléfono pudo recortar energía: se avisa en la columna `aviso`.

Salidas en --salida (por defecto, junto al export): `<nombre>_espectro.csv`, `<nombre>_espectro.md` y, si hay
matplotlib, `<nombre>_espectro.png`. No modifica el export.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from analysis import senales  # noqa: E402

MARGEN_NYQUIST = 0.8   # f_E por encima del 80 % de fs_nativa/2 = posible recorte (aviso)


def _senales(acc, fs: float) -> dict[str, np.ndarray]:
    acc_u = senales.remuestrear(acc, fs)
    xyz = acc_u[["ax", "ay", "az"]].to_numpy()
    norma = np.linalg.norm(xyz, axis=1)
    con_g = bool(np.median(norma) > 5.0)          # phyphox con g da ~9,8 m/s² en reposo; sin g, ~0
    salida = {"vertical": senales.eje_vertical(acc_u, fs, con_g=con_g), "magnitud": norma - norma.mean()}
    for i, eje in enumerate("xyz"):
        salida[eje] = xyz[:, i] - xyz[:, i].mean()
    return salida


def analizar(ruta, fraccion: float = 0.95) -> tuple[list[dict], dict]:
    """Devuelve (filas de la tabla, espectros por señal) para un export de phyphox."""
    acc, _ = senales.cargar_phyphox(ruta)
    t = acc["t"].to_numpy()
    if len(t) < 64:
        raise ValueError(f"{ruta}: muy pocas muestras de aceleración ({len(t)})")
    fs = senales.tasa_nativa(t)
    filas, espectros = [], {}
    for nombre, x in _senales(acc, fs).items():
        e = senales.espectro(x, fs, fraccion)
        espectros[nombre] = e
        filas.append(dict(senal=nombre, muestras=len(x), duracion_s=round(len(x) / fs, 2), fs_nativa_hz=round(fs, 2),
                          fraccion=fraccion, f_energia_hz=round(e.f_energia, 2), fs_minima_hz=round(e.fs_minima, 2),
                          fs_recomendada_hz=round(e.fs_recomendada, 2),
                          aviso="f_E cerca de Nyquist: el teléfono pudo recortar" if e.f_energia > MARGEN_NYQUIST * fs / 2
                          else ""))
    return filas, espectros


def _escribir(filas: list[dict], espectros: dict, base: Path, nombre: str) -> list[Path]:
    base.mkdir(parents=True, exist_ok=True)
    rutas = [base / f"{nombre}_espectro.csv", base / f"{nombre}_espectro.md"]
    with open(rutas[0], "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    cab = list(filas[0])
    md = [f"# Espectro de `{nombre}`", "", "| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
    md += ["| " + " | ".join(str(f[c]) for c in cab) + " |" for f in filas]
    v = next(f for f in filas if f["senal"] == "vertical")
    md += ["", f"Recomendación (eje vertical): muestrear a **≥ {v['fs_recomendada_hz']} Hz** "
               f"(Nyquist con margen: 2,5 × f_E = 2,5 × {v['f_energia_hz']} Hz)."]
    rutas[1].write_text("\n".join(md) + "\n", encoding="utf-8")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib no está instalado: se omite el gráfico (tabla CSV y Markdown listas).")
        return rutas
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for nombre_s, e in espectros.items():
        ax.semilogy(e.f, e.psd, lw=1.6 if nombre_s == "vertical" else 0.8, label=nombre_s)
    e = espectros["vertical"]
    ax.axvline(e.f_energia, ls="--", color="k", lw=1, label=f"{e.fraccion:.0%} energía (vertical): {e.f_energia:.1f} Hz")
    ax.set_xlabel("frecuencia (Hz)")
    ax.set_ylabel("PSD ((m/s²)²/Hz)")
    ax.set_title(f"Espectro de {nombre}")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    rutas.append(base / f"{nombre}_espectro.png")
    fig.savefig(rutas[-1], dpi=200)
    plt.close(fig)
    return rutas


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("export", help="CSV, carpeta o .zip exportado por phyphox")
    ap.add_argument("--salida", help="carpeta de salida (por defecto, la del export)")
    ap.add_argument("--fraccion", type=float, default=0.95, help="fracción de la energía (por defecto 0.95)")
    a = ap.parse_args(argv)
    ruta = Path(a.export)
    filas, espectros = analizar(ruta, a.fraccion)
    nombre = ruta.stem if ruta.suffix else ruta.name
    for r in _escribir(filas, espectros, Path(a.salida) if a.salida else ruta.parent, nombre):
        print(r)
    v = next(f for f in filas if f["senal"] == "vertical")
    print(f"Eje vertical: {a.fraccion:.0%} de la energía bajo {v['f_energia_hz']} Hz → fs mínima {v['fs_minima_hz']} Hz,"
          f" recomendada {v['fs_recomendada_hz']} Hz (nativa {v['fs_nativa_hz']} Hz). {v['aviso']}".rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
