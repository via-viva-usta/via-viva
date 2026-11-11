"""Prepara la carpeta del tablero en línea (`web/en_linea/`) para publicarla en Netlify.

    viaviva nube preparar     → web/en_linea/config.js (URL y clave PÚBLICA de Supabase, desde .env)
                                 web/en_linea/datos/tramos.geojson (calles de OSM con id_tramo, desde la base local)
Los dos archivos están en .gitignore. La clave de servicio NUNCA va a la página (solo la usa la Pi para sincronizar).
Pasos completos (crear el proyecto, pegar el SQL, usuarios, publicar): docs/NUBE.md.
"""
from __future__ import annotations

import argparse
import json
import os

from viaviva import config
from viaviva.almacen import conectar
from viaviva.estructuras import leer_wkt_linea

SITIO = config.RAIZ / "web" / "en_linea"


def tramos_geojson(url_db: str | None = None) -> dict:
    con = conectar(url_db)
    try:
        feats = []
        for t, nombre, tipo, barrio, largo, wkt in con.execute(
                "SELECT id_tramo, nombre, tipo_via, barrio, longitud_m, geometria_wkt FROM tramos"):
            feats.append({"type": "Feature", "id": t,
                          "properties": {"id": t, "n": nombre, "t": tipo, "b": barrio, "l": round(largo or 0)},
                          "geometry": {"type": "LineString",
                                       "coordinates": [[round(lo, 5), round(la, 5)] for la, lo in leer_wkt_linea(wkt)]}})
    finally:
        con.close()
    return {"type": "FeatureCollection", "fuente": "© OpenStreetMap (ODbL)", "features": feats}


def preparar(url_db: str | None = None) -> dict:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    publica = os.getenv("SUPABASE_CLAVE_PUBLICA", "")
    if publica and publica == os.getenv("SUPABASE_CLAVE", ""):
        raise SystemExit("SUPABASE_CLAVE_PUBLICA es igual a la clave de servicio: NO se publica. Use la clave anon.")
    (SITIO / "datos").mkdir(parents=True, exist_ok=True)
    (SITIO / "config.js").write_text(
        "// Generado por `viaviva nube preparar` (no se sube a Git). La clave anon es pública por diseño: sin sesión\n"
        "// no lee nada (RLS en viaviva/supabase_esquema.sql).\n"
        f"window.VIAVIVA = {json.dumps({'supabaseUrl': url, 'supabaseClave': publica}, ensure_ascii=False)};\n",
        encoding="utf-8")
    g = tramos_geojson(url_db)
    (SITIO / "datos" / "tramos.geojson").write_text(json.dumps(g, ensure_ascii=False, separators=(",", ":")),
                                                     encoding="utf-8")
    kb = (SITIO / "datos" / "tramos.geojson").stat().st_size / 1024
    return {"config": bool(url and publica), "tramos": len(g["features"]), "kb_geojson": round(kb)}


def main():
    ap = argparse.ArgumentParser(prog="viaviva nube", description=__doc__.splitlines()[0])
    ap.add_argument("accion", choices=["preparar"])
    ap.parse_args()
    r = preparar()
    print(f"Listo: {r['tramos']} tramos ({r['kb_geojson']} KB) en {SITIO / 'datos'}.")
    if not r["config"]:
        print("Falta SUPABASE_URL o SUPABASE_CLAVE_PUBLICA en .env: la página no podrá conectarse (docs/NUBE.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
