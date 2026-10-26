"""Modelo de riesgo por tramo: regresión logística y bosque aleatorio con validación espacial por barrios.

Entrada: tabla variables_tramo (python -m risk_model.variables).
Entrena solo con tramos de etiqueta conocida (1 = hueco, 0 = revisado sin hueco) y predice todos.

Validación espacial: GroupKFold con el barrio como grupo, así cada pliegue deja fuera barrios
COMPLETOS (CLAUDE.md, sección 7). Para mostrar cuánto se infla una validación ingenua, también
se reporta la AUC con pliegues al azar; la que vale para el informe es la espacial.

Salidas:
  tabla riesgo                        probabilidad y ranking de cada tramo (con --guardar)
  data/campo/visita_<fecha>.csv       10 tramos de mayor riesgo NO reportados + 10 al azar (con --lista-campo)

Uso (desde via-viva/):
  etl\\.venv\\Scripts\\python -m risk_model.modelo                      # entrena y valida (datos reales)
  etl\\.venv\\Scripts\\python -m risk_model.modelo --guardar --lista-campo
  etl\\.venv\\Scripts\\python -m risk_model.modelo --demo-sintetico     # PRUEBA del código con etiquetas inventadas

Con --demo-sintetico las etiquetas se inventan a partir de una fórmula: las métricas que imprime
NO son resultados del proyecto. Si además se usa --guardar, la corrida queda en la tabla riesgo con
version_modelo 'DEMO-SINTETICO' para que el tablero la muestre con un aviso.
"""
from __future__ import annotations

import argparse
import json
from datetime import date

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold, StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from etl.config import DATA
from etl.db import ahora_utc, conectar

CATEGORICAS = ["tipo_via", "clase_superficie"]
NUMERICAS = ["longitud_m", "pendiente_pct", "lluvia_30d_mm", "lluvia_max_dia_mm", "huecos_vecinos",
             "accidentes_cercanos", "rugosidad_media", "profundidad_max_mm"]
MIN_ETIQUETADOS = 30          # por debajo de esto no tiene sentido entrenar
MIN_POR_CLASE = 5
MIN_GRUPOS = 3
VERSION_DEMO = "DEMO-SINTETICO"
AVISO_DEMO = ("*" * 78 + "\n*  DEMO SINTÉTICA: las etiquetas son INVENTADAS con una fórmula.\n"
              "*  Las métricas de abajo solo prueban que el código corre. NO son resultados.\n" + "*" * 78)


def preprocesador(numericas: list[str]) -> ColumnTransformer:
    return ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAS),
        ("num", make_pipeline(SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler()),
         numericas),
    ])


def modelos(numericas: list[str], semilla: int = 0) -> dict:
    return {
        "logistica": make_pipeline(preprocesador(numericas),
                                   LogisticRegression(max_iter=2000, class_weight="balanced")),
        "bosque": make_pipeline(preprocesador(numericas),
                                RandomForestClassifier(n_estimators=300, min_samples_leaf=3,
                                                       class_weight="balanced", random_state=semilla, n_jobs=-1)),
    }


def cargar(con) -> pd.DataFrame:
    v = pd.read_sql("SELECT v.*, t.nombre, t.lat_centro, t.lon_centro FROM variables_tramo v "
                    "JOIN tramos t USING (id_tramo)", con)
    if v.empty:
        raise SystemExit("variables_tramo está vacía: corre primero python -m risk_model.variables")
    return v


def etiquetas_sinteticas(v: pd.DataFrame, fraccion: float = 0.3, semilla: int = 0) -> pd.Series:
    """Inventa etiquetas para probar el código: más riesgo con pendiente, sin pavimentar y vías residenciales,
    y un efecto por barrio (para que la validación espacial tenga algo que medir). NO describe Tunja."""
    rng = np.random.default_rng(semilla)
    efecto_barrio = v["barrio"].map({b: rng.normal(0, 0.8) for b in v["barrio"].dropna().unique()}).fillna(0)
    logit = (-1.5 + 0.08 * v["pendiente_pct"].fillna(5) + 1.2 * (v["clase_superficie"] == "sin_pavimentar")
             + 0.5 * (v["tipo_via"] == "residential") + 0.02 * (v["lluvia_30d_mm"].fillna(90) - 90)
             + efecto_barrio + rng.normal(0, 0.5, len(v)))
    y = (rng.random(len(v)) < 1 / (1 + np.exp(-logit))).astype(float)
    revisados = rng.random(len(v)) < fraccion            # solo una parte de los tramos "se revisó"
    return pd.Series(np.where(revisados, y, np.nan), index=v.index)


def verificar_datos(et: pd.DataFrame, grupo: str):
    n = len(et)
    por_clase = et["etiqueta"].value_counts().to_dict()
    grupos = et[grupo].nunique()
    faltas = []
    if n < MIN_ETIQUETADOS:
        faltas.append(f"hay {n} tramos etiquetados (mínimo {MIN_ETIQUETADOS})")
    if min(por_clase.get(0, 0), por_clase.get(1, 0)) < MIN_POR_CLASE:
        faltas.append(f"por clase: {por_clase} (mínimo {MIN_POR_CLASE} de cada una)")
    if grupos < MIN_GRUPOS:
        faltas.append(f"hay {grupos} {grupo}s con etiquetas (mínimo {MIN_GRUPOS})")
    if faltas:
        raise SystemExit(
            "No hay datos suficientes para entrenar con datos reales:\n  - " + "\n  - ".join(faltas) +
            "\nFuentes de etiquetas: eventos 'hueco' del nodo, reportes ciudadanos, data/alcaldia/huecos.csv y "
            "data/campo/tramos_revisados.csv (id_tramo, tiene_hueco).\n"
            "Para probar el código sin datos: python -m risk_model.modelo --demo-sintetico")


def validar(v: pd.DataFrame, grupo: str, semilla: int = 0) -> dict:
    et = v[v["etiqueta"].notna()].reset_index(drop=True)
    verificar_datos(et, grupo)
    numericas = [c for c in NUMERICAS if et[c].notna().any()]   # columnas sin ningún dato no aportan
    X, y, g = et[CATEGORICAS + numericas], et["etiqueta"].astype(int), et[grupo].fillna("sin_grupo")
    k = min(5, g.nunique())
    res = {"n": len(et), "positivos": int(y.sum()), "grupos": int(g.nunique()), "pliegues": k,
           "numericas": numericas}
    for nombre, modelo in modelos(numericas, semilla).items():
        p_esp = cross_val_predict(modelo, X, y, groups=g, cv=GroupKFold(n_splits=k), method="predict_proba")[:, 1]
        auc_pliegue = []
        for _, prueba in GroupKFold(n_splits=k).split(X, y, g):
            if y.iloc[prueba].nunique() == 2:
                auc_pliegue.append(roc_auc_score(y.iloc[prueba], p_esp[prueba]))
        p_azar = cross_val_predict(modelo, X, y, cv=StratifiedKFold(k, shuffle=True, random_state=semilla),
                                   method="predict_proba")[:, 1]
        res[nombre] = {"auc_espacial": roc_auc_score(y, p_esp), "auc_por_pliegue": auc_pliegue,
                       "auc_azar": roc_auc_score(y, p_azar)}
    return res


def predecir(v: pd.DataFrame, numericas: list[str], semilla: int = 0) -> dict:
    et = v[v["etiqueta"].notna()]
    salida = {}
    for nombre, modelo in modelos(numericas, semilla).items():
        modelo.fit(et[CATEGORICAS + numericas], et["etiqueta"].astype(int))
        salida[nombre] = modelo.predict_proba(v[CATEGORICAS + numericas])[:, 1]
    return salida


def guardar_riesgo(con, v: pd.DataFrame, probs: dict, version: str, numericas: list[str]) -> str:
    fecha = ahora_utc()
    reportado = (v["etiqueta"] == 1).astype(int)
    with con:
        for nombre, p in probs.items():
            orden = (-p).argsort().argsort() + 1     # rango 1 = más riesgo
            filas = []
            for i, (idt, prob) in enumerate(zip(v["id_tramo"], p)):
                variables = {c: (None if pd.isna(v.at[i, c]) else
                                 (v.at[i, c].item() if hasattr(v.at[i, c], "item") else v.at[i, c]))
                             for c in CATEGORICAS + numericas}
                filas.append((int(idt), nombre, version, fecha, float(prob), int(orden[i]), int(reportado.iat[i]),
                              json.dumps(variables, ensure_ascii=False)))
            con.executemany("INSERT INTO riesgo (id_tramo, modelo, version_modelo, fecha_calculo, probabilidad, "
                            "rango, reportado, variables_json) VALUES (?,?,?,?,?,?,?,?)", filas)
    return fecha


def lista_campo(v: pd.DataFrame, p: np.ndarray, k: int = 10, semilla: int = 0, demo: bool = False):
    """Métrica central del proyecto: top-k de riesgo NO reportados vs. k tramos al azar NO reportados."""
    no_rep = v.assign(probabilidad=p)[v["etiqueta"] != 1]
    top = no_rep.nlargest(k, "probabilidad").assign(grupo="top_riesgo")
    azar = no_rep.drop(top.index).sample(k, random_state=semilla).assign(grupo="azar")
    lista = pd.concat([top, azar])[["grupo", "id_tramo", "nombre", "barrio", "tipo_via", "probabilidad",
                                    "lat_centro", "lon_centro"]]
    lista["tiene_hueco"] = ""        # se llena en campo y vuelve como data/campo/tramos_revisados.csv
    carpeta = DATA / "campo"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"visita_{date.today().isoformat()}{'_DEMO' if demo else ''}.csv"
    lista.to_csv(ruta, index=False, encoding="utf-8")
    return ruta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grupo", choices=["barrio", "sector"], default="barrio",
                    help="unidad que se deja fuera completa en la validación espacial")
    ap.add_argument("--guardar", action="store_true", help="escribe la tabla riesgo")
    ap.add_argument("--lista-campo", action="store_true", help="genera la lista de visita top-10 vs. azar")
    ap.add_argument("--demo-sintetico", action="store_true", help="usa etiquetas INVENTADAS para probar el código")
    ap.add_argument("--version", default=f"v0.1-{date.today().isoformat()}")
    args = ap.parse_args()

    con = conectar()
    v = cargar(con)
    version = args.version
    if args.demo_sintetico:
        print(AVISO_DEMO)
        v["etiqueta"] = etiquetas_sinteticas(v)
        version = VERSION_DEMO

    r = validar(v, args.grupo)
    print(f"\nTramos etiquetados: {r['n']} ({r['positivos']} con hueco) en {r['grupos']} {args.grupo}s; "
          f"GroupKFold con {r['pliegues']} pliegues")
    print(f"Variables numéricas usadas: {', '.join(r['numericas'])}")
    for nombre in ("logistica", "bosque"):
        m = r[nombre]
        pl = ", ".join(f"{a:.2f}" for a in m["auc_por_pliegue"])
        print(f"  {nombre:<10} AUC espacial {m['auc_espacial']:.3f} (pliegues: {pl}) · "
              f"AUC con pliegues al azar {m['auc_azar']:.3f}")
    if args.demo_sintetico:
        print(AVISO_DEMO)

    if args.guardar or args.lista_campo:
        probs = predecir(v, r["numericas"])
        if args.guardar:
            fecha = guardar_riesgo(con, v, probs, version, r["numericas"])
            print(f"Guardado en riesgo: version_modelo='{version}', fecha_calculo={fecha}")
        if args.lista_campo:
            ruta = lista_campo(v, probs["bosque"], demo=args.demo_sintetico)
            print(f"Lista de visita de campo: {ruta}")


if __name__ == "__main__":
    main()
