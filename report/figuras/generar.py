"""Genera las figuras del informe a partir de la base del repositorio (datos reales, no inventados).

Uso (desde via-viva/):  analysis\\.venv\\Scripts\\python report\\figuras\\generar.py

  tunja_tramos.pdf   grafo de calles de Tunja por tipo de vía (OpenStreetMap)
  pendiente.pdf      histograma de la pendiente por tramo (SRTM 30 m)
  lluvia.pdf         lluvia diaria de las estaciones IDEAM usadas
  datos_figuras.tex  macros con las cifras de la base (\\NTramos, \\NNodos, ...) para que el texto no las copie a mano
Las figuras de resultados (espectro, E1–E4, detector, riesgo) las generan analysis/experimentos.py y los scripts de
entrenamiento cuando haya datos reales.
"""
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
sys.path.insert(0, str(RAIZ))
from db.acceso import conectar  # noqa: E402

plt.rcParams.update({"font.size": 8, "font.family": "serif", "axes.spines.top": False, "axes.spines.right": False})
COLORES_VIA = {"trunk": "#7f0d1e", "primary": "#c8331f", "secondary": "#e9672b", "tertiary": "#f3a33a",
               "unclassified": "#9e9e9e", "residential": "#bdbdbd"}


def coords(wkt):
    cuerpo = wkt[wkt.index("(") + 1:wkt.rindex(")")]
    xy = np.array([p.split() for p in cuerpo.split(",")], dtype=float)
    return xy[:, 0], xy[:, 1]


def main():
    con = conectar()
    t = pd.read_sql("SELECT tipo_via, longitud_m, pendiente_pct, geometria_wkt FROM tramos", con)
    t["tipo"] = t["tipo_via"].fillna("otro").str.split(";").str[0].str.replace("_link", "", regex=False)

    # 1) grafo de Tunja (zona urbana)
    fig, ax = plt.subplots(figsize=(3.4, 3.6))
    for tipo in ["residential", "unclassified", "tertiary", "secondary", "primary", "trunk"]:
        sub = t[t["tipo"] == tipo]
        for w in sub["geometria_wkt"]:
            x, y = coords(w)
            ax.plot(x, y, color=COLORES_VIA[tipo], lw=0.35 if tipo == "residential" else 0.9, solid_capstyle="round")
        ax.plot([], [], color=COLORES_VIA[tipo], lw=1.5, label=f"{tipo} ({len(sub)})")
    ax.set_xlim(-73.392, -73.335)
    ax.set_ylim(5.500, 5.580)
    ax.set_aspect(1 / np.cos(np.radians(5.54)))
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.legend(loc="lower right", fontsize=6, frameon=True, framealpha=0.9, edgecolor="none")
    ax.text(0.01, 0.01, "© OpenStreetMap contributors", transform=ax.transAxes, fontsize=5, color="#555")
    fig.tight_layout()
    fig.savefig(AQUI / "tunja_tramos.pdf")
    plt.close(fig)

    # 2) pendiente
    p = t["pendiente_pct"].dropna()
    fig, ax = plt.subplots(figsize=(3.4, 1.8))
    ax.hist(p.clip(upper=30), bins=30, color="#e9672b")
    ax.set_xlabel("segment slope (%)  [values > 30 % grouped at 30]")
    ax.set_ylabel("segments")
    fig.tight_layout()
    fig.savefig(AQUI / "pendiente.pdf")
    plt.close(fig)

    # 3) lluvia
    ll = pd.read_sql("SELECT titulo, ts_dato, valor FROM fuentes_externas WHERE tipo = 'clima' "
                     "AND variable = 'precipitacion_diaria_mm' ORDER BY ts_dato", con)
    fig, ax = plt.subplots(figsize=(3.4, 1.8))
    for nombre, g in ll.groupby("titulo"):
        ax.plot(pd.to_datetime(g["ts_dato"]), g["valor"], lw=0.8, label=nombre.split(" [")[0].split(" - ")[0][:22].title())
    ax.set_ylabel("daily rainfall (mm)")
    ax.legend(fontsize=5, frameon=False, ncol=2)
    ax.tick_params(axis="x", labelsize=6, rotation=30)
    fig.tight_layout()
    fig.savefig(AQUI / "lluvia.pdf")
    plt.close(fig)

    # 4) cifras para el texto
    n_nodos = con.execute("SELECT COUNT(*) FROM nodos").fetchone()[0]
    n_barrios = con.execute("SELECT COUNT(*) FROM barrios").fetchone()[0]
    n_est = ll["titulo"].str.extract(r"\[(\d+)\]")[0].nunique() or ll["titulo"].nunique()
    con_sup = pd.read_sql("SELECT COUNT(*) n FROM tramos WHERE superficie IS NOT NULL", con)["n"][0]
    macros = {
        "NTramos": f"{len(t):,}".replace(",", "\\,"), "NNodos": f"{n_nodos:,}".replace(",", "\\,"),
        "KmTramos": f"{t['longitud_m'].sum() / 1000:.1f}", "PctSuperficie": f"{100 * con_sup / len(t):.0f}",
        "NPendiente": f"{len(p):,}".replace(",", "\\,"), "PendMediana": f"{p.median():.1f}",
        "PendPnoventa": f"{p.quantile(0.9):.1f}", "NBarrios": str(n_barrios), "NEstaciones": str(n_est),
        "LluviaDesde": ll["ts_dato"].min() if len(ll) else "--", "LluviaHasta": ll["ts_dato"].max() if len(ll) else "--",
    }
    (AQUI / "datos_figuras.tex").write_text(
        "% Generado por report/figuras/generar.py desde la base del repositorio. No editar a mano.\n" +
        "".join(f"\\newcommand{{\\{k}}}{{{v}}}\n" for k, v in macros.items()), encoding="utf-8")
    print("Figuras y macros generadas:", ", ".join(f"{k}={v}" for k, v in macros.items()))


if __name__ == "__main__":
    main()
