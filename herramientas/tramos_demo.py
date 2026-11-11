"""Calles de Tunja para ver el tablero en línea en modo DEMO sin la base local (por ejemplo, en un Mac sin data/).

    python herramientas/tramos_demo.py      → web/en_linea/datos/tramos.geojson (ignorado por Git)
    luego: cd web/en_linea && python -m http.server 8765   y abrir http://127.0.0.1:8765/tablero.html?demo=1 (la portada: http://127.0.0.1:8765/)

OJO: baja las VÍAS de OpenStreetMap por Overpass. Sus números son ids de vías OSM, NO el id_tramo de la base
(que sale de osmnx: un tramo por cada cuadra entre cruces). Sirve para ?demo=1, donde el riesgo también se inventa con
esos números. Para publicar en Netlify use `viaviva nube preparar`, que genera el archivo con id_tramo y barrio.
El archivo queda marcado con "demo": true y la página avisa si se usa sin ?demo=1.
© OpenStreetMap contributors (ODbL).
"""
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

SALIDA = Path(__file__).resolve().parent.parent / "web" / "en_linea" / "datos" / "tramos.geojson"
TIPOS = "motorway|trunk|primary|secondary|tertiary|residential|unclassified|living_street"
CONSULTA = f'[out:json][timeout:90];way["highway"~"^({TIPOS})$"](5.49,-73.40,5.58,-73.32);out geom;'
CABECERAS = {"User-Agent": "via-viva-demo/1.0 (proyecto universitario USTA Tunja)"}
ESPEJOS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]


def bajar() -> dict:
    for url in ESPEJOS:
        try:
            pedido = urllib.request.Request(url, data=urllib.parse.urlencode({"data": CONSULTA}).encode(),
                                            headers=CABECERAS)
            with urllib.request.urlopen(pedido, timeout=120) as r:
                return json.load(r)
        except Exception as e:                       # Overpass a veces responde 502/504: se prueba el espejo
            print("Falló", url, e)
    raise SystemExit("No se pudo descargar OpenStreetMap.")


def largo_m(c: list[list[float]]) -> float:
    return sum(6371000 * math.hypot(math.radians(b[0] - a[0]) * math.cos(math.radians(a[1])),
                                    math.radians(b[1] - a[1])) for a, b in zip(c, c[1:]))


def main() -> None:
    feats = []
    for w in bajar()["elements"]:
        c = [[round(p["lon"], 5), round(p["lat"], 5)] for p in w.get("geometry", [])]
        if len(c) < 2:
            continue
        tg = w.get("tags", {})
        feats.append({"type": "Feature", "id": w["id"], "geometry": {"type": "LineString", "coordinates": c},
                      "properties": {"id": w["id"], "n": tg.get("name"), "t": tg.get("highway"), "b": None,
                                     "l": round(largo_m(c))}})
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    datos = {"type": "FeatureCollection", "demo": True,
             "fuente": "DEMO: vías de OSM por Overpass (herramientas/tramos_demo.py); ids de vía OSM, no id_tramo. "
                       "© OpenStreetMap contributors (ODbL)",
             "features": feats}
    SALIDA.write_text(json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("Listo:", len(feats), "vías (DEMO) en", SALIDA)


if __name__ == "__main__":
    main()
