"""Elevación de los nodos del grafo y pendiente de cada tramo.

Fuente: OpenTopoData (api.opentopodata.org), conjunto SRTM 30 m (NASA, dominio público).
Límites de la API pública: 100 puntos por consulta y 1 consulta por segundo (aquí se espera 2 s).
Solo se consultan los nodos que aún no tienen elevación, así que se puede volver a correr.

Pendiente del tramo = |elev(u) - elev(v)| / longitud × 100 (%).
Ojo: SRTM tiene celdas de ~30 m y error vertical de varios metros; en tramos cortos la
pendiente es poco confiable. Por eso se deja NULL en tramos de menos de 30 m.

Uso (desde via-viva/):
  etl\\.venv\\Scripts\\python -m etl.elevacion
"""
from etl.db import conectar
from etl.scraping.comun import ClienteRespetuoso

URL = "https://api.opentopodata.org/v1/srtm30m"
FUENTE = "OpenTopoData srtm30m"
LOTE = 100
LONGITUD_MINIMA_M = 30.0


def elevaciones_faltantes(con, cliente) -> int:
    pendientes = con.execute("SELECT osm_id, lat, lon FROM nodos WHERE elevacion_m IS NULL").fetchall()
    hechas = 0
    for i in range(0, len(pendientes), LOTE):
        lote = pendientes[i:i + LOTE]
        locs = "|".join(f"{lat:.6f},{lon:.6f}" for _, lat, lon in lote)
        datos = cliente.get(URL, params={"locations": locs}).json()
        if datos.get("status") != "OK":
            raise RuntimeError(f"OpenTopoData respondió: {datos}")
        with con:
            con.executemany(
                "UPDATE nodos SET elevacion_m = ?, fuente_elev = ? WHERE osm_id = ?",
                [(r["elevation"], FUENTE, osm_id) for (osm_id, _, _), r in zip(lote, datos["results"])],
            )
        hechas += len(lote)
        print(f"  {hechas}/{len(pendientes)} nodos")
    return hechas


def calcular_pendientes(con) -> int:
    with con:
        con.execute("""
            UPDATE tramos SET pendiente_pct = (
                SELECT CASE WHEN tramos.longitud_m >= ? AND nu.elevacion_m IS NOT NULL AND nv.elevacion_m IS NOT NULL
                            THEN ABS(nu.elevacion_m - nv.elevacion_m) / tramos.longitud_m * 100.0 END
                FROM nodos nu, nodos nv WHERE nu.osm_id = tramos.osm_u AND nv.osm_id = tramos.osm_v)
        """, (LONGITUD_MINIMA_M,))
    return con.execute("SELECT COUNT(*) FROM tramos WHERE pendiente_pct IS NOT NULL").fetchone()[0]


def main():
    con = conectar()
    if con.execute("SELECT COUNT(*) FROM nodos").fetchone()[0] == 0:
        raise SystemExit("La tabla nodos está vacía: corre primero python -m etl.osm_tunja")
    print(f"Consultando elevaciones en {URL} ...")
    elevaciones_faltantes(con, ClienteRespetuoso())
    n = calcular_pendientes(con)
    total = con.execute("SELECT COUNT(*) FROM tramos").fetchone()[0]
    emin, emax = con.execute("SELECT MIN(elevacion_m), MAX(elevacion_m) FROM nodos").fetchone()
    pend = [r[0] for r in con.execute("SELECT pendiente_pct FROM tramos WHERE pendiente_pct IS NOT NULL "
                                      "ORDER BY pendiente_pct")]
    print(f"Elevación de nodos: {emin:.0f} a {emax:.0f} m")
    print(f"Tramos con pendiente: {n} de {total} (los de < {LONGITUD_MINIMA_M:.0f} m quedan en NULL)")
    if pend:
        print(f"Pendiente: mediana {pend[len(pend) // 2]:.1f} %, percentil 90 {pend[int(len(pend) * 0.9)]:.1f} %, "
              f"máxima {pend[-1]:.1f} %")


if __name__ == "__main__":
    main()
