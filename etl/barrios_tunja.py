"""Barrios y veredas de Tunja (datos abiertos de la Alcaldía) → tabla barrios.

Fuente: datos.gov.co, conjunto 4ryc-k7fx "Información Barrios y veredas de Municipio de Tunja, Boyacá"
(Alcaldía de Tunja). Trae un punto de referencia por barrio o vereda y su sector; no trae polígonos.
Es un conjunto publicado como dato abierto; aun así se consulta con el cliente que respeta robots.txt.

Uso (desde via-viva/):
  etl\\.venv\\Scripts\\python -m etl.barrios_tunja
"""
from etl.config import SOCRATA_APP_TOKEN
from etl.db import ahora_utc, conectar
from etl.scraping.comun import ClienteRespetuoso

DATASET = "4ryc-k7fx"
URL_API = f"https://www.datos.gov.co/resource/{DATASET}.json"
FUENTE = f"Alcaldía de Tunja (datos.gov.co {DATASET})"


def descargar() -> list[dict]:
    params = {"$limit": 5000, "$order": "id"}
    if SOCRATA_APP_TOKEN:
        params["$$app_token"] = SOCRATA_APP_TOKEN
    return ClienteRespetuoso().get(URL_API, params=params).json()


def main():
    filas, descartadas = [], 0
    fecha = ahora_utc()
    for b in descargar():
        try:
            filas.append((int(b["id"]), b["barrio"].strip().title(), b.get("sector"),
                          1 if b.get("esvereda") in (True, "true") else 0,
                          float(b["latitud"]), float(b["longitud"]), FUENTE, fecha))
        except (KeyError, TypeError, ValueError):
            descartadas += 1
    con = conectar()
    with con:
        con.executemany(
            """
            INSERT INTO barrios (id_barrio, nombre, sector, es_vereda, lat, lon, fuente, fecha_carga)
            VALUES (?,?,?,?,?,?,?,?)
            ON CONFLICT (id_barrio) DO UPDATE SET nombre=excluded.nombre, sector=excluded.sector,
                es_vereda=excluded.es_vereda, lat=excluded.lat, lon=excluded.lon, fecha_carga=excluded.fecha_carga
            """,
            filas,
        )
    n, veredas, sectores = con.execute(
        "SELECT COUNT(*), SUM(es_vereda), COUNT(DISTINCT sector) FROM barrios").fetchone()
    print(f"Barrios cargados: {n} ({veredas} veredas, {sectores} sectores). Filas descartadas: {descartadas}")


if __name__ == "__main__":
    main()
