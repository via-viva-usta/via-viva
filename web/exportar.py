"""Exporta de SQLite a web/datos.js lo que muestra el mapa público (sin backend).

Qué sale (y qué NO):
  * tramos (geometría OSM, © OpenStreetMap contributors, ODbL) con su riesgo de la corrida elegida;
  * reportes ciudadanos: tipo, estado, fecha y ubicación. NO sale la foto, ni el hash del usuario, ni la descripción;
  * eventos detectados (nodo y recorridos etiquetados): clase, fecha y ubicación. NO sale el hash del vehículo;
  * NINGÚN dato de la Alcaldía (data/alcaldia/ no se lee aquí) ni personal.

datos.js asigna window.VIA_VIVA = {...}: así index.html abre con doble clic, sin servidor.

Uso (desde via-viva/):
  etl\\.venv\\Scripts\\python web\\exportar.py                 # corrida más reciente que no sea DEMO (o la DEMO si no hay otra)
  etl\\.venv\\Scripts\\python web\\exportar.py --sin-riesgo
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from db.acceso import ahora_utc, conectar  # noqa: E402

SALIDA = Path(__file__).resolve().parent / "datos.js"
DECIMALES = 5          # ~1 m: suficiente para el mapa y reduce el tamaño


def coords_wkt(wkt: str) -> list[list[float]]:
    cuerpo = wkt[wkt.index("(") + 1:wkt.rindex(")")]
    return [[round(float(x), DECIMALES), round(float(y), DECIMALES)]
            for x, y in (p.split() for p in cuerpo.split(","))]


def elegir_corrida(con):
    filas = con.execute("SELECT modelo, version_modelo, fecha_calculo FROM riesgo GROUP BY 1, 2, 3 "
                        "ORDER BY fecha_calculo DESC, modelo = 'bosque' DESC").fetchall()
    reales = [f for f in filas if not f[1].upper().startswith("DEMO")]
    return (reales or filas or [None])[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sin-riesgo", action="store_true")
    args = ap.parse_args()
    con = conectar(aplicar_esquema=False)

    corrida = None if args.sin_riesgo else elegir_corrida(con)
    riesgo = {}
    if corrida:
        riesgo = dict(con.execute("SELECT id_tramo, probabilidad FROM riesgo WHERE modelo = ? AND version_modelo = ? "
                                  "AND fecha_calculo = ?", corrida).fetchall())
    tramos = []
    for idt, nombre, tipo, wkt in con.execute("SELECT id_tramo, nombre, tipo_via, geometria_wkt FROM tramos"):
        p = riesgo.get(idt)
        tramos.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords_wkt(wkt)},
                       "properties": {"id": idt, "n": nombre, "t": tipo, "r": None if p is None else round(p, 3)}})
    reportes = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, DECIMALES), round(lat, DECIMALES)]},
                 "properties": {"id": i, "tipo": t, "estado": e, "fecha": f[:10]}}
                for i, t, e, f, lat, lon in con.execute(
                    "SELECT id_reporte, tipo, estado, ts_utc, lat, lon FROM reportes WHERE estado <> 'descartado'")]
    eventos = [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [round(lon, DECIMALES), round(lat, DECIMALES)]},
                "properties": {"clase": c, "origen": o, "fecha": (f or "")[:10]}}
               for c, o, f, lat, lon in con.execute(
                   "SELECT clase, origen, ts_utc, lat, lon FROM eventos WHERE clase IN "
                   "('hueco', 'resalto', 'impacto_fuerte', 'obstaculo') AND origen <> 'simulado'")]
    datos = {
        "generado": ahora_utc(),
        "corrida": None if corrida is None else {"modelo": corrida[0], "version": corrida[1], "fecha": corrida[2],
                                                 "demo": corrida[1].upper().startswith("DEMO")},
        "tramos": {"type": "FeatureCollection", "features": tramos},
        "reportes": {"type": "FeatureCollection", "features": reportes},
        "eventos": {"type": "FeatureCollection", "features": eventos},
    }
    texto = "// Generado por web/exportar.py — no editar a mano. © OpenStreetMap contributors (ODbL).\n" \
            "window.VIA_VIVA = " + json.dumps(datos, ensure_ascii=False, separators=(",", ":")) + ";\n"
    SALIDA.write_text(texto, encoding="utf-8")
    print(f"{SALIDA}: {len(tramos)} tramos ({len(riesgo)} con riesgo), {len(reportes)} reportes, "
          f"{len(eventos)} eventos, {SALIDA.stat().st_size / 1e6:.1f} MB · corrida: "
          f"{'ninguna' if corrida is None else ' · '.join(corrida)}")


if __name__ == "__main__":
    main()
