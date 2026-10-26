"""Descarga el grafo de calles de Tunja (OpenStreetMap, osmnx) y lo carga a SQLite.

Salidas:
  data/osm/tunja_drive.gpkg     GeoPackage con capas 'nodes' y 'edges' (se abre en QGIS)
  data/osm/tunja_drive.graphml  grafo completo para volver a cargarlo sin descargar
  tabla tramos en la base SQLite (una fila por tramo NO dirigido)

Uso (desde la carpeta via-viva/):
  etl\\.venv\\Scripts\\python -m etl.osm_tunja
  etl\\.venv\\Scripts\\python -m etl.osm_tunja --lugar "Tunja, Boyacá, Colombia" --red drive

Datos © colaboradores de OpenStreetMap, licencia ODbL.
"""
import argparse
import time

import osmnx as ox

from etl import geohash
from etl.config import OSM_DIR
from etl.db import ahora_utc, conectar


def _texto(valor):
    """osmnx a veces entrega listas (vía con varias etiquetas): se unen con ';'."""
    if valor is None:
        return None
    if isinstance(valor, float) and valor != valor:  # NaN
        return None
    if isinstance(valor, (list, tuple, set)):
        return ";".join(str(v) for v in valor)
    return str(valor)


# Servidores Overpass públicos. El principal se satura a veces (502/504):
# se reintenta con espera creciente y luego se prueba el siguiente.
SERVIDORES_OVERPASS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.private.coffee/api",
]


def descargar(lugar: str, red: str, intentos_por_servidor: int = 2):
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(OSM_DIR / "cache")
    # osmnx no conserva 'surface' ni 'smoothness' por defecto; son variables del modelo de riesgo
    extra = [t for t in ("surface", "smoothness") if t not in ox.settings.useful_tags_way]
    ox.settings.useful_tags_way = list(ox.settings.useful_tags_way) + extra
    ultimo_error = None
    for servidor in SERVIDORES_OVERPASS:
        ox.settings.overpass_url = servidor
        espera = 15
        for intento in range(1, intentos_por_servidor + 1):
            print(f"Descargando grafo '{red}' de: {lugar} ({servidor}, intento {intento}) ...")
            try:
                return ox.graph_from_place(lugar, network_type=red, simplify=True)
            except Exception as e:  # osmnx lanza varios tipos según el error HTTP
                ultimo_error = e
                print(f"  Falló: {str(e).splitlines()[0]}. Esperando {espera} s ...")
                time.sleep(espera)
                espera *= 2
    raise RuntimeError(f"No se pudo descargar el grafo de ningún servidor: {ultimo_error}")


def guardar_archivos(G, nombre: str):
    OSM_DIR.mkdir(parents=True, exist_ok=True)
    gpkg = OSM_DIR / f"{nombre}.gpkg"
    graphml = OSM_DIR / f"{nombre}.graphml"
    ox.save_graph_geopackage(G, filepath=gpkg)
    ox.save_graphml(G, filepath=graphml)
    return gpkg, graphml


def cargar_tramos(G_no_dirigido) -> int:
    """Inserta (o actualiza) un tramo por cada arista del grafo no dirigido."""
    aristas = ox.graph_to_gdfs(G_no_dirigido, nodes=False, edges=True)
    fecha = ahora_utc()
    filas = []
    for (u, v, k), a in aristas.iterrows():
        geom = a.geometry
        medio = geom.interpolate(0.5, normalized=True)
        filas.append((
            int(u), int(v), int(k),
            _texto(a.get("osmid")),
            _texto(a.get("name")),
            _texto(a.get("highway")),
            _texto(a.get("surface")),
            _texto(a.get("lanes")),
            _texto(a.get("maxspeed")),
            1 if a.get("oneway") is True else 0,
            float(a["length"]),
            medio.y, medio.x,
            geohash.codificar(medio.y, medio.x, 7),
            geom.wkt,
            fecha,
        ))
    con = conectar()
    with con:
        con.executemany(
            """
            INSERT INTO tramos (osm_u, osm_v, osm_key, osm_way_ids, nombre, tipo_via, superficie,
                                carriles, vel_max, un_sentido, longitud_m, lat_centro, lon_centro,
                                geohash7, geometria_wkt, fecha_carga)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT (osm_u, osm_v, osm_key) DO UPDATE SET
                osm_way_ids=excluded.osm_way_ids, nombre=excluded.nombre, tipo_via=excluded.tipo_via,
                superficie=excluded.superficie, carriles=excluded.carriles, vel_max=excluded.vel_max,
                un_sentido=excluded.un_sentido, longitud_m=excluded.longitud_m,
                lat_centro=excluded.lat_centro, lon_centro=excluded.lon_centro,
                geohash7=excluded.geohash7, geometria_wkt=excluded.geometria_wkt,
                fecha_carga=excluded.fecha_carga
            """,
            filas,
        )
    total = con.execute("SELECT COUNT(*) FROM tramos").fetchone()[0]
    con.close()
    return total


def resumen(G, G_nd, total_db: int):
    aristas = ox.graph_to_gdfs(G_nd, nodes=False, edges=True)
    km = aristas["length"].sum() / 1000
    tipos = aristas["highway"].map(_texto).value_counts().head(8)
    con_superficie = aristas["surface"].notna().mean() * 100 if "surface" in aristas else 0.0
    print("\n=== Grafo de calles ===")
    print(f"Nodos (intersecciones y extremos): {G.number_of_nodes()}")
    print(f"Aristas dirigidas (osmnx):         {G.number_of_edges()}")
    print(f"Tramos no dirigidos:               {G_nd.number_of_edges()}")
    print(f"Tramos en la tabla 'tramos':       {total_db}")
    print(f"Longitud total de tramos:          {km:.1f} km")
    print(f"Tramos con etiqueta 'surface':     {con_superficie:.1f} %")
    print("Tramos por tipo de vía (top 8):")
    for tipo, n in tipos.items():
        print(f"  {tipo:<28} {n}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--lugar", default="Tunja, Boyacá, Colombia")
    p.add_argument("--red", default="drive", help="network_type de osmnx: drive, drive_service, all ...")
    p.add_argument("--nombre", default="tunja_drive", help="nombre base de los archivos de salida")
    args = p.parse_args()

    G = descargar(args.lugar, args.red)
    gpkg, graphml = guardar_archivos(G, args.nombre)
    print(f"Guardado: {gpkg}\nGuardado: {graphml}")

    G_nd = ox.convert.to_undirected(G)  # una calle de doble sentido = un tramo
    total = cargar_tramos(G_nd)
    resumen(G, G_nd, total)


if __name__ == "__main__":
    main()
