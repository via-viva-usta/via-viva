"""Construye la tabla variables_tramo: una fila por tramo con las variables del modelo de riesgo.

Variables (CLAUDE.md, sección 7):
  tipo_via, clase_superficie, longitud_m        ← OpenStreetMap (tabla tramos)
  pendiente_pct                                  ← etl.elevacion (SRTM 30 m)
  lluvia_30d_mm, lluvia_max_dia_mm               ← IDEAM (fuentes_externas), interpolada por distancia inversa (IDW)
  huecos_vecinos                                 ← huecos conocidos a <= 300 m en OTROS tramos
  accidentes_cercanos                            ← siniestros a <= 200 m
  rugosidad_media, profundidad_max_mm            ← eventos del nodo asignados al tramo
  barrio, sector                                 ← punto de barrio más cercano (Alcaldía, datos abiertos)
  etiqueta (1 / 0 / NULL)                        ← huecos conocidos en el tramo y revisiones de campo

Huecos conocidos = eventos 'hueco' del nodo + reportes ciudadanos 'hueco' (no descartados)
                   + inventario de la Alcaldía si existe data/alcaldia/huecos.csv (columnas lat, lon).
Tramos revisados (etiqueta 0 o 1) = data/campo/tramos_revisados*.csv (columnas id_tramo, tiene_hueco[, fuente]):
  los escribe etl.recorridos (recorridos etiquetados) y se agregan los de las visitas de campo.
Cada etiqueta guarda su fuente (alcaldia, recorrido, visita, nodo, bot) en fuente_etiqueta, para que el modelo
pueda entrenar con la Alcaldía o con el plan B (recorridos + bot) y registrar cuál usó.
Los eventos con origen 'simulado' no cuentan, salvo con --incluir-simulados (pruebas).
Siniestros = data/alcaldia/siniestros.csv (lat, lon) + noticias de accidentes con coordenadas.

Uso (desde via-viva/):
  etl\\.venv\\Scripts\\python -m risk_model.variables
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import wkt

from etl.config import DATA
from etl.db import ahora_utc, conectar

CRS_METROS = "EPSG:32618"     # UTM 18N: Tunja está en lon -73,4
RADIO_HUECOS_M = 300
RADIO_ACCIDENTES_M = 200
MAX_DIST_ASIGNACION_M = 30    # un punto se asigna a un tramo si está a <= 30 m
DIAS_LLUVIA = 30

TIPOS = ["trunk", "primary", "secondary", "tertiary", "unclassified", "residential"]
PAVIMENTADA = {"asphalt", "paved", "concrete", "concrete:plates", "concrete:lanes", "paving_stones", "sett",
               "cobblestone", "bricks"}
SIN_PAVIMENTAR = {"unpaved", "gravel", "fine_gravel", "dirt", "ground", "compacted", "earth", "sand", "grass",
                  "mud", "pebblestone"}

ARCHIVO_HUECOS_ALCALDIA = DATA / "alcaldia" / "huecos.csv"
ARCHIVO_SINIESTROS = DATA / "alcaldia" / "siniestros.csv"
CARPETA_CAMPO = DATA / "campo"            # tramos_revisados*.csv: recorridos (etl.recorridos) y visitas de campo


# ---------------------------------------------------------------------------
# Limpieza de etiquetas OSM
# ---------------------------------------------------------------------------
def agrupar_tipo(highway: str | None) -> str:
    if not isinstance(highway, str) or not highway:  # None o NaN
        return "otro"
    base = highway.split(";")[0].replace("_link", "")
    return base if base in TIPOS else "otro"


def agrupar_superficie(surface: str | None) -> str:
    if not isinstance(surface, str) or not surface:  # None o NaN
        return "desconocida"
    s = surface.split(";")[0]
    if s in PAVIMENTADA:
        return "pavimentada"
    if s in SIN_PAVIMENTAR:
        return "sin_pavimentar"
    return "desconocida"


# ---------------------------------------------------------------------------
# Lectura de fuentes
# ---------------------------------------------------------------------------
def leer_tramos(con) -> gpd.GeoDataFrame:
    df = pd.read_sql("SELECT id_tramo, tipo_via, superficie, longitud_m, pendiente_pct, lat_centro, lon_centro, "
                     "geometria_wkt FROM tramos", con)
    g = gpd.GeoDataFrame(df, geometry=df.pop("geometria_wkt").map(wkt.loads), crs="EPSG:4326")
    return g.to_crs(CRS_METROS)


def _puntos(df: pd.DataFrame) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326").to_crs(CRS_METROS)


def _leer_csv_latlon(ruta) -> pd.DataFrame:
    if not ruta.exists():
        return pd.DataFrame(columns=["lat", "lon"])
    df = pd.read_csv(ruta, sep=None, engine="python")
    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns={"latitud": "lat", "longitud": "lon", "latitude": "lat", "longitude": "lon"})
    return df[["lat", "lon"]].apply(pd.to_numeric, errors="coerce").dropna()


def leer_huecos(con, incluir_simulados: bool = False) -> gpd.GeoDataFrame:
    filtro = "" if incluir_simulados else " AND origen <> 'simulado'"
    partes = [
        pd.read_sql("SELECT lat, lon, CASE origen WHEN 'phyphox' THEN 'recorrido' WHEN 'simulado' THEN 'recorrido' "
                    f"ELSE 'nodo' END AS origen FROM eventos WHERE clase = 'hueco'{filtro}", con),
        pd.read_sql("SELECT lat, lon, 'bot' AS origen FROM reportes "
                    "WHERE tipo = 'hueco' AND estado <> 'descartado'", con),
        _leer_csv_latlon(ARCHIVO_HUECOS_ALCALDIA).assign(origen="alcaldia"),
    ]
    return _puntos(pd.concat(partes, ignore_index=True))


def leer_siniestros(con) -> gpd.GeoDataFrame:
    partes = [
        _leer_csv_latlon(ARCHIVO_SINIESTROS),
        pd.read_sql("SELECT lat, lon FROM fuentes_externas WHERE tipo = 'accidente' "
                    "AND lat IS NOT NULL AND lon IS NOT NULL", con),
    ]
    return _puntos(pd.concat(partes, ignore_index=True))


def leer_eventos(con) -> gpd.GeoDataFrame:
    return _puntos(pd.read_sql("SELECT lat, lon, rugosidad, profundidad_mm FROM eventos", con))


def leer_lluvia(con) -> pd.DataFrame:
    """Por estación: lluvia acumulada y máxima diaria de los últimos DIAS_LLUVIA días con datos."""
    df = pd.read_sql("SELECT json_extract(extra_json, '$.codigoestacion') AS estacion, lat, lon, ts_dato, valor "
                     "FROM fuentes_externas WHERE tipo = 'clima' AND variable = 'precipitacion_diaria_mm'", con)
    if df.empty:
        return df
    df["ts_dato"] = pd.to_datetime(df["ts_dato"])
    df = df[df["ts_dato"] > df["ts_dato"].max() - pd.Timedelta(days=DIAS_LLUVIA)]
    return df.groupby(["estacion", "lat", "lon"], as_index=False).agg(
        lluvia_30d_mm=("valor", "sum"), lluvia_max_dia_mm=("valor", "max"), dias=("valor", "size"))


# ---------------------------------------------------------------------------
# Cálculo de variables
# ---------------------------------------------------------------------------
def idw(lat, lon, est: pd.DataFrame, columna: str, potencia: float = 2.0) -> np.ndarray:
    """Interpolación por distancia inversa desde las estaciones (distancias en km, haversine)."""
    if est.empty:
        return np.full(len(lat), np.nan)
    p1, p2 = np.radians(lat)[:, None], np.radians(est["lat"].to_numpy())[None, :]
    dl = np.radians(est["lon"].to_numpy())[None, :] - np.radians(lon)[:, None]
    d = 2 * 6371 * np.arcsin(np.sqrt(np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2))
    w = 1.0 / np.maximum(d, 0.05) ** potencia
    return (w * est[columna].to_numpy()[None, :]).sum(axis=1) / w.sum(axis=1)


def asignar_a_tramo(puntos: gpd.GeoDataFrame, tramos: gpd.GeoDataFrame) -> pd.Series:
    """id_tramo más cercano a cada punto (NaN si está a más de MAX_DIST_ASIGNACION_M)."""
    if puntos.empty:
        return pd.Series(dtype="float64")
    j = gpd.sjoin_nearest(puntos, tramos[["id_tramo", "geometry"]], how="left",
                          max_distance=MAX_DIST_ASIGNACION_M)
    return j[~j.index.duplicated()]["id_tramo"]


def contar_cerca(tramos: gpd.GeoDataFrame, puntos: gpd.GeoDataFrame, radio: float,
                 excluir: pd.Series | None = None) -> np.ndarray:
    """Cuántos puntos hay a <= radio de cada tramo (excluyendo los asignados al propio tramo)."""
    if puntos.empty:
        return np.zeros(len(tramos), dtype=int)
    pts = puntos.assign(tramo_del_punto=excluir if excluir is not None else np.nan)
    zonas = tramos[["id_tramo", "geometry"]].copy()
    zonas["geometry"] = zonas.buffer(radio)
    j = gpd.sjoin(pts, zonas, predicate="within")
    j = j[j["tramo_del_punto"] != j["id_tramo"]]
    conteo = j.groupby("id_tramo").size()
    return tramos["id_tramo"].map(conteo).fillna(0).astype(int).to_numpy()


def asignar_barrio(tramos: gpd.GeoDataFrame, con) -> pd.DataFrame:
    b = pd.read_sql("SELECT nombre, sector, lat, lon FROM barrios", con)
    if b.empty:
        return pd.DataFrame({"barrio": None, "sector": None, "distancia_barrio_m": np.nan}, index=tramos.index)
    centros = gpd.GeoDataFrame(tramos[["id_tramo"]], geometry=tramos.geometry.interpolate(0.5, normalized=True),
                               crs=CRS_METROS)
    j = gpd.sjoin_nearest(centros, _puntos(b), how="left", distance_col="distancia_barrio_m")
    j = j[~j.index.duplicated()]
    return j.rename(columns={"nombre": "barrio"})[["barrio", "sector", "distancia_barrio_m"]]


def leer_revisados(carpeta) -> pd.DataFrame:
    """Une todos los tramos_revisados*.csv: id_tramo, tiene_hueco y fuente (recorrido o visita)."""
    partes = []
    for ruta in sorted(carpeta.glob("tramos_revisados*.csv")) if carpeta.exists() else []:
        r = pd.read_csv(ruta, sep=None, engine="python")
        r.columns = [c.strip().lower() for c in r.columns]
        fuente = "visita" if "visita" in ruta.stem else "recorrido"
        partes.append(pd.DataFrame({"id_tramo": r["id_tramo"].astype(int),
                                    "tiene_hueco": pd.to_numeric(r["tiene_hueco"], errors="coerce"),
                                    "fuente": fuente}).dropna(subset=["tiene_hueco"]))
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=["id_tramo", "tiene_hueco", "fuente"])


def etiquetas(tramos, huecos: gpd.GeoDataFrame, tramo_de_hueco: pd.Series, carpeta_campo=None) -> tuple[pd.Series, pd.Series]:
    """1 si alguna fuente vio un hueco en el tramo; 0 si fue revisado y nadie vio huecos; NULL si no se sabe.
    La fuente guarda TODAS las que aportaron, separadas por ';' (p. ej. 'bot;recorrido')."""
    fuentes = {}                                   # id_tramo → (etiqueta, {fuentes})
    for idt, origen in zip(tramo_de_hueco.reindex(huecos.index), huecos["origen"]):
        if pd.notna(idt):
            fuentes.setdefault(int(idt), [1, set()])[1].add(origen)
    for _, r in leer_revisados(carpeta_campo or CARPETA_CAMPO).iterrows():
        e = fuentes.setdefault(int(r["id_tramo"]), [0, set()])
        e[0] = max(e[0], int(r["tiene_hueco"]))
        e[1].add(r["fuente"])
    et = tramos["id_tramo"].map(lambda i: fuentes[i][0] if i in fuentes else np.nan)
    fuente = tramos["id_tramo"].map(lambda i: ";".join(sorted(fuentes[i][1])) if i in fuentes else None)
    return et, fuente


def construir(con, incluir_simulados: bool = False, carpeta_campo=None) -> pd.DataFrame:
    tramos = leer_tramos(con)
    v = pd.DataFrame({"id_tramo": tramos["id_tramo"]})
    v["tipo_via"] = tramos["tipo_via"].map(agrupar_tipo)
    v["clase_superficie"] = tramos["superficie"].map(agrupar_superficie)
    v["longitud_m"] = tramos["longitud_m"]
    v["pendiente_pct"] = tramos["pendiente_pct"]

    lluvia = leer_lluvia(con)
    lat, lon = tramos["lat_centro"].to_numpy(), tramos["lon_centro"].to_numpy()
    v["lluvia_30d_mm"] = idw(lat, lon, lluvia, "lluvia_30d_mm") if not lluvia.empty else np.nan
    v["lluvia_max_dia_mm"] = idw(lat, lon, lluvia, "lluvia_max_dia_mm") if not lluvia.empty else np.nan

    huecos = leer_huecos(con, incluir_simulados)
    tramo_de_hueco = asignar_a_tramo(huecos, tramos)
    v["huecos_vecinos"] = contar_cerca(tramos, huecos, RADIO_HUECOS_M,
                                       excluir=tramo_de_hueco.reindex(huecos.index))
    v["accidentes_cercanos"] = contar_cerca(tramos, leer_siniestros(con), RADIO_ACCIDENTES_M)

    ev = leer_eventos(con)
    if not ev.empty:
        ev["id_tramo"] = asignar_a_tramo(ev, tramos)
        agg = ev.groupby("id_tramo").agg(rugosidad_media=("rugosidad", "mean"),
                                         profundidad_max_mm=("profundidad_mm", "max"))
        v = v.join(agg, on="id_tramo")
    else:
        v["rugosidad_media"] = np.nan
        v["profundidad_max_mm"] = np.nan

    v = v.join(asignar_barrio(tramos, con))
    v["etiqueta"], v["fuente_etiqueta"] = etiquetas(tramos, huecos, tramo_de_hueco, carpeta_campo)
    v["fecha_calculo"] = ahora_utc()
    return v, len(huecos), len(lluvia)


def guardar(con, v: pd.DataFrame):
    cols = ["id_tramo", "fecha_calculo", "tipo_via", "clase_superficie", "longitud_m", "pendiente_pct",
            "lluvia_30d_mm", "lluvia_max_dia_mm", "huecos_vecinos", "accidentes_cercanos", "rugosidad_media",
            "profundidad_max_mm", "barrio", "sector", "distancia_barrio_m", "etiqueta", "fuente_etiqueta"]
    filas = [tuple(None if pd.isna(x) else (x.item() if hasattr(x, "item") else x) for x in fila)
             for fila in v[cols].itertuples(index=False)]
    with con:
        con.execute("DELETE FROM variables_tramo")
        con.executemany(f"INSERT INTO variables_tramo ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                        filas)
        con.executemany("UPDATE tramos SET barrio = ? WHERE id_tramo = ?",
                        [(b, int(t)) for t, b in zip(v["id_tramo"], v["barrio"])])


def main():
    import argparse
    from pathlib import Path
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--campo", default=str(CARPETA_CAMPO), help="carpeta con tramos_revisados*.csv")
    ap.add_argument("--incluir-simulados", action="store_true", help="cuenta eventos con origen 'simulado' (pruebas)")
    args = ap.parse_args()
    con = conectar()
    v, n_huecos, n_estaciones = construir(con, args.incluir_simulados, Path(args.campo))
    guardar(con, v)
    print(f"variables_tramo: {len(v)} tramos")
    print(f"  tipo_via: {v['tipo_via'].value_counts().to_dict()}")
    print(f"  clase_superficie: {v['clase_superficie'].value_counts().to_dict()}")
    print(f"  pendiente_pct: {v['pendiente_pct'].notna().sum()} con valor")
    print(f"  lluvia_30d_mm (IDW de {n_estaciones} estaciones): "
          f"{v['lluvia_30d_mm'].min():.1f} a {v['lluvia_30d_mm'].max():.1f} mm")
    print(f"  huecos conocidos usados: {n_huecos}")
    print(f"  barrios asignados: {v['barrio'].nunique()} (distancia mediana al punto del barrio "
          f"{v['distancia_barrio_m'].median():.0f} m)")
    print(f"  etiquetas: 1 = {int((v['etiqueta'] == 1).sum())}, 0 = {int((v['etiqueta'] == 0).sum())}, "
          f"sin etiqueta = {int(v['etiqueta'].isna().sum())}")
    if v["fuente_etiqueta"].notna().any():
        print(f"  fuentes de las etiquetas: {v['fuente_etiqueta'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
