"""Tablas y gráficas de los experimentos de arquitectura E1–E4 (y memoria y corriente) para el informe.

Entrada (copiada de la microSD del nodo; ver docs/experimentos.md):
  data/raw/nodo/**/exp_NNN.csv     filas t_ms,experimento,condicion,variable,valor (las escribe el firmware)
  data/raw/nodo/corriente.csv      medidas con el tester USB: estado,minutos,mah_inicio,mah_fin,voltaje_v

Salida:
  analysis/salidas/experimentos.md          resumen legible
  report/tablas/e1.tex, e2e3.tex, e4.tex, mem.tex, corriente.tex   tablas que el informe incluye si existen
  report/figuras/e1_jitter.pdf, e3_latencia.pdf

Uso (desde via-viva/):
  analysis\\.venv\\Scripts\\python analysis\\experimentos.py
  analysis\\.venv\\Scripts\\python analysis\\experimentos.py --ejemplo   # prueba con un archivo de EJEMPLO inventado (salida a una carpeta temporal)
"""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
MODOS = ["polling", "int_muestra", "fifo_dma"]
NOMBRE_MODO = {"polling": "Polling (5 ms)", "int_muestra": "Per-sample interrupt", "fifo_dma": "FIFO + DMA ping-pong"}  # en inglés: van al informe


def leer(carpeta: Path) -> pd.DataFrame:
    partes = []
    for ruta in sorted(carpeta.rglob("exp_*.csv")):
        df = pd.read_csv(ruta)
        df["archivo"] = str(ruta.relative_to(carpeta))
        partes.append(df)
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()


def tabla_e1(df: pd.DataFrame) -> pd.DataFrame:
    e = df[df["experimento"] == "E1"].pivot_table(index=["archivo", "condicion", "t_ms"], columns="variable",
                                                  values="valor").reset_index()
    if e.empty:
        return e
    e = e.sort_values("t_ms")
    e = e[e.groupby(["archivo", "condicion"]).cumcount() > 0]   # se descarta el 1.er intervalo (arranque)
    filas = []
    for modo, g in e.groupby("condicion"):
        filas.append({"modo": modo, "minutos": g["segundos"].sum() / 60,
                      "perdidas_pct": 100 * (g["esperadas"].sum() - g["muestras"].sum()) / g["esperadas"].sum(),
                      "overruns": int(g["overruns"].sum()), "bloques_perdidos": int(g["bloques_perdidos"].sum()),
                      "jitter_us": g["jitter_us"].mean(), "max_us": g["max_us"].max(),
                      "cpu1_pct": g["cpu1_pct"].mean(), "cpu0_pct": g["cpu0_pct"].mean(),
                      "lectura_pct": g["lectura_ocupada_pct"].mean()})
    t = pd.DataFrame(filas)
    t["orden"] = t["modo"].map({m: i for i, m in enumerate(MODOS)})
    return t.sort_values("orden").drop(columns="orden")


def tabla_lat(df: pd.DataFrame, exp: str) -> pd.DataFrame:
    e = df[(df["experimento"] == exp) & df["variable"].str.endswith("_us")]
    if e.empty:
        return e
    e = e.assign(medida=e["variable"].str.rsplit("_", n=2).str[-2])
    t = e.pivot_table(index="condicion", columns="medida", values="valor", aggfunc="mean").reset_index()
    if {"media", "desv"} <= set(t.columns):            # R7: media ± desviación estándar (Welford en el nodo)
        t["media_desv_us"] = [f"{m:.1f} ± {d:.1f}" for m, d in zip(t["media"], t["desv"])]
    return t


def tabla_e4(df: pd.DataFrame) -> pd.DataFrame:
    e = df[df["experimento"] == "E4"]
    return e.pivot_table(index="condicion", columns="variable", values="valor", aggfunc="mean").reset_index() if len(e) else e


def tabla_corriente(ruta: Path) -> pd.DataFrame:
    if not ruta.exists():
        return pd.DataFrame()
    c = pd.read_csv(ruta)
    c["ma"] = (c["mah_fin"] - c["mah_inicio"]) / (c["minutos"] / 60)
    c["mw"] = c["ma"] * c["voltaje_v"]
    return c[["estado", "minutos", "ma", "voltaje_v", "mw"]]


def a_latex(t: pd.DataFrame, columnas: dict, titulo: str, etiqueta: str, aviso: str = "") -> str:
    enc = " & ".join(columnas.values())
    filas = []
    for _, f in t.iterrows():
        celdas = []
        for c in columnas:
            v = f.get(c, np.nan)
            celdas.append(str(v).replace("_", r"\_") if isinstance(v, str) else ("--" if pd.isna(v) else f"{v:.1f}" if abs(v) < 1000 else f"{v:,.0f}"))
        filas.append(" & ".join(celdas) + r" \\")
    nota = f"\n\\par\\footnotesize {aviso}" if aviso else ""
    return (f"\\begin{{table}}[!t]\n\\centering\n\\caption{{{titulo}}}\n\\label{{{etiqueta}}}\n\\footnotesize\n"
            f"\\begin{{tabular}}{{l{'r' * (len(columnas) - 1)}}}\n\\toprule\n{enc} \\\\\n\\midrule\n" + "\n".join(filas) +
            f"\n\\bottomrule\n\\end{{tabular}}{nota}\n\\end{{table}}\n")


def graficas(e1: pd.DataFrame, e23: pd.DataFrame, carpeta: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    if len(e1):
        fig, ax = plt.subplots(figsize=(3.4, 2.2))
        ax.bar([NOMBRE_MODO.get(m, m).replace(" ", "\n", 1) for m in e1["modo"]], e1["jitter_us"], color="#e9672b")
        ax.set_ylabel("jitter (µs)")
        ax.tick_params(axis="x", labelsize=7)
        fig.tight_layout()
        fig.savefig(carpeta / "e1_jitter.pdf")
        plt.close(fig)
    if len(e23):
        fig, ax = plt.subplots(figsize=(3.4, 2.2))
        ax.barh(e23["condicion"], e23["media"], color="#7f0d1e")
        ax.set_xlabel("latencia media (µs)")
        ax.tick_params(axis="y", labelsize=7)
        fig.tight_layout()
        fig.savefig(carpeta / "e3_latencia.pdf")
        plt.close(fig)


def generar_ejemplo(carpeta: Path):
    """Archivo de EJEMPLO con números inventados, solo para probar el lector. Nunca va al informe."""
    rng = np.random.default_rng(0)
    filas = []
    for modo in MODOS:
        for k in range(12):
            esp = 1000.0
            v = {"segundos": 5.0, "muestras": esp - rng.integers(0, 3), "esperadas": esp, "overruns": 0,
                 "bloques_perdidos": 0, "timeouts": 0, "intervalo_us": 5000, "jitter_us": rng.uniform(5, 50),
                 "min_us": 4900, "max_us": 5200, "lectura_ocupada_pct": rng.uniform(1, 5), "cpu0_pct": rng.uniform(5, 20),
                 "cpu1_pct": rng.uniform(1, 10), "heap_libre_B": 200000}
            filas += [(k * 5000, "E1", modo, var, val) for var, val in v.items()]
    for exp, cond in [("E2", "flash_f32"), ("E2", "sram_f32"), ("E3", "f32_sram"), ("E3", "i8_sram"), ("E3", "i8_flash")]:
        for med in ("primera", "media", "desv", "min", "max"):
            filas.append((0, exp, cond, f"cnn_{med}_us", rng.uniform(100, 900)))
    for cond in ("i2c_400k_14B", "spi_1M5_8B"):
        filas += [(0, "E4", cond, "lectura_media_us", rng.uniform(20, 400)), (0, "E4", cond, "us_por_byte", rng.uniform(3, 30))]
    filas.append((0, "MEM", "arranque", "heap_libre_B", 210000))
    (carpeta / "sesion_ejemplo").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(filas, columns=["t_ms", "experimento", "condicion", "variable", "valor"]).to_csv(
        carpeta / "sesion_ejemplo" / "exp_001.csv", index=False)
    pd.DataFrame([{"estado": "nodo completo", "minutos": 10, "mah_inicio": 0, "mah_fin": 25, "voltaje_v": 5.05}]).to_csv(
        carpeta / "corriente.csv", index=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--carpeta", default=str(RAIZ / "data" / "raw" / "nodo"))
    ap.add_argument("--ejemplo", action="store_true", help="prueba el lector con números INVENTADOS (salida temporal)")
    args = ap.parse_args()

    if args.ejemplo:
        base = Path(tempfile.mkdtemp(prefix="exp_ejemplo_"))
        carpeta, sal_md, sal_tab, sal_fig = base / "nodo", base, base, base
        generar_ejemplo(carpeta)
        aviso = "EJEMPLO con números inventados: no es un resultado."
        print(f"*** {aviso} Salida en {base} ***")
    else:
        carpeta = Path(args.carpeta)
        sal_md = RAIZ / "analysis" / "salidas"
        sal_tab, sal_fig = RAIZ / "report" / "tablas", RAIZ / "report" / "figuras"
        aviso = ""
    df = leer(carpeta)
    if df.empty:
        raise SystemExit(f"No hay archivos exp_*.csv en {carpeta}. Copiarlos de la microSD (ver docs/experimentos.md).")
    for d in (sal_md, sal_tab, sal_fig):
        d.mkdir(parents=True, exist_ok=True)

    e1, e2, e3, e4 = tabla_e1(df), tabla_lat(df, "E2"), tabla_lat(df, "E3"), tabla_e4(df)
    mem = df[df["experimento"] == "MEM"].groupby("variable")["valor"].mean().reset_index()
    cor = tabla_corriente(carpeta / "corriente.csv")
    e23 = pd.concat([e2.assign(condicion="E2 " + e2["condicion"]) if len(e2) else e2,
                     e3.assign(condicion="E3 " + e3["condicion"]) if len(e3) else e3])

    md = [f"# Experimentos de arquitectura — {len(df['archivo'].unique())} archivo(s) de {carpeta}", ""]
    if aviso:
        md += [f"> **{aviso}**", ""]
    for titulo, t in (("E1 — modo de adquisición", e1), ("E2/E3 — latencia de inferencia (µs)", e23),
                      ("E4 — I2C vs. SPI", e4), ("Memoria", mem), ("Corriente", cor)):
        md += [f"## {titulo}", "", t.to_markdown(index=False, floatfmt=".1f") if len(t) else "_sin datos_", ""]
    (sal_md / ("experimentos_EJEMPLO.md" if args.ejemplo else "experimentos.md")).write_text("\n".join(md), encoding="utf-8")

    if len(e1):
        e1t = e1.assign(modo=e1["modo"].map(NOMBRE_MODO))
        (sal_tab / "e1.tex").write_text(a_latex(e1t, {"modo": "Mode", "perdidas_pct": "Lost (\\%)", "overruns": "Overruns",
                                                       "jitter_us": "Jitter ($\\mu$s)", "max_us": "Max int. ($\\mu$s)",
                                                       "cpu1_pct": "CPU1 (\\%)"},
                                                 "E1: acquisition mode (measured on the node).", "tab:e1", aviso), encoding="utf-8")
    if len(e23):
        (sal_tab / "e2e3.tex").write_text(a_latex(e23, {"condicion": "Configuration", "primera": "First ($\\mu$s)",
                                                        "media": "Mean ($\\mu$s)", "max": "Max ($\\mu$s)"},
                                                  "E2/E3: inference latency on the ESP32.", "tab:e2e3", aviso), encoding="utf-8")
    if len(e4):
        cols = {"condicion": "Bus"} | {c: c.replace("_", " ") for c in e4.columns if c != "condicion"}
        (sal_tab / "e4.tex").write_text(a_latex(e4, cols, "E4: I$^2$C vs. SPI read time.", "tab:e4", aviso), encoding="utf-8")
    if len(cor):
        (sal_tab / "corriente.tex").write_text(a_latex(cor, {"estado": "State", "ma": "Current (mA)", "mw": "Power (mW)"},
                                                       "Node current (USB tester).", "tab:corriente", aviso), encoding="utf-8")
    graficas(e1, e23, sal_fig)
    print("\n".join(md))


if __name__ == "__main__":
    main()
