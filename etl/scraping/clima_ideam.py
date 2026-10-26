"""Lluvia diaria de estaciones IDEAM cercanas a Tunja → tabla fuentes_externas.

Fuente: datos abiertos de Colombia (datos.gov.co), conjunto s54a-sgyg
"Datos Hidrometeorológicos Crudos - Red de Estaciones IDEAM: Precipitación" (API Socrata/SoQL).
Es una API pública pensada para acceso automatizado; aun así se revisa robots.txt
y se respeta su Crawl-delay.

Ojo: son datos CRUDOS (sin validación de IDEAM). Pueden tener huecos o valores atípicos.
La fecha de observación se interpreta como hora local de Colombia (UTC-5).

Uso (desde via-viva/):
  etl\\.venv\\Scripts\\python -m etl.scraping.clima_ideam               # últimos 30 días, estaciones a <=15 km
  etl\\.venv\\Scripts\\python -m etl.scraping.clima_ideam --dias 90 --radio-km 25
"""
import argparse
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

from etl.config import SOCRATA_APP_TOKEN, TUNJA_LAT, TUNJA_LON
from etl.db import conectar
from etl.scraping.comun import ClienteRespetuoso, guardar, hash_contenido

DATASET = "s54a-sgyg"
URL_API = f"https://www.datos.gov.co/resource/{DATASET}.json"
FUENTE = f"IDEAM (datos.gov.co {DATASET})"
PAGINA = 50000


def distancia_km(lat1, lon1, lat2, lon2) -> float:
    """Distancia de gran círculo (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def _params(**kw):
    if SOCRATA_APP_TOKEN:
        kw["$$app_token"] = SOCRATA_APP_TOKEN
    return kw


def estaciones_cercanas(cliente, desde: str, radio_km: float) -> list[dict]:
    """Estaciones de Boyacá con datos desde 'desde' y a menos de radio_km del centro de Tunja.

    El nombre del departamento cambia de formato en el tiempo ('BOYACÁ' / 'Boyacá'),
    por eso se filtra con upper(...) like y luego por distancia real.
    """
    r = cliente.get(URL_API, params=_params(**{
        "$select": "codigoestacion, nombreestacion, municipio, latitud, longitud, count(*) as n",
        "$where": f"upper(departamento) like 'BOYAC%' AND fechaobservacion >= '{desde}'",
        "$group": "codigoestacion, nombreestacion, municipio, latitud, longitud",
        "$limit": 5000,
    }))
    estaciones = {}
    for e in r.json():
        e["km"] = distancia_km(TUNJA_LAT, TUNJA_LON, float(e["latitud"]), float(e["longitud"]))
        if e["km"] <= radio_km:
            # una estación sale dos veces si cambió de nombre: se deja la de más datos
            previa = estaciones.get(e["codigoestacion"])
            if previa is None or int(e["n"]) > int(previa["n"]):
                estaciones[e["codigoestacion"]] = e
    return sorted(estaciones.values(), key=lambda e: e["km"])


def observaciones(cliente, codigo: str, desde: str) -> list[dict]:
    filas, offset = [], 0
    while True:
        r = cliente.get(URL_API, params=_params(**{
            "$select": "fechaobservacion, valorobservado",
            "$where": f"codigoestacion = '{codigo}' AND fechaobservacion >= '{desde}'",
            "$order": "fechaobservacion",
            "$limit": PAGINA,
            "$offset": offset,
        }))
        lote = r.json()
        filas.extend(lote)
        if len(lote) < PAGINA:
            return filas
        offset += PAGINA


def lluvia_diaria(obs: list[dict]) -> dict:
    """Suma por día local, sin duplicados por fecha de observación.

    También estima la cobertura del día: n_obs * intervalo / 1440 min.
    """
    por_instante = {}
    for o in obs:
        try:
            por_instante[o["fechaobservacion"]] = float(o["valorobservado"])
        except (KeyError, TypeError, ValueError):
            continue
    instantes = sorted(datetime.fromisoformat(t) for t in por_instante)
    difs = [(b - a).total_seconds() / 60 for a, b in zip(instantes, instantes[1:])]
    intervalo = Counter(difs).most_common(1)[0][0] if difs else 60.0  # moda del intervalo

    dias = defaultdict(lambda: {"mm": 0.0, "n": 0, "max_mm": 0.0})
    for t, mm in por_instante.items():
        d = dias[t[:10]]
        d["mm"] += mm
        d["n"] += 1
        d["max_mm"] = max(d["max_mm"], mm)
    for d in dias.values():
        d["cobertura"] = min(1.0, d["n"] * intervalo / 1440)
        d["intervalo_min"] = intervalo
    return dict(dias)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dias", type=int, default=30, help="días hacia atrás desde hoy")
    p.add_argument("--radio-km", type=float, default=15.0)
    args = p.parse_args()

    desde = (date.today() - timedelta(days=args.dias)).isoformat() + "T00:00:00"
    cliente = ClienteRespetuoso()
    if not cliente.permitido(URL_API):
        raise SystemExit("robots.txt de datos.gov.co no permite la API: no se descarga nada.")

    estaciones = estaciones_cercanas(cliente, desde, args.radio_km)
    print(f"Estaciones con datos desde {desde[:10]} a <= {args.radio_km} km de Tunja: {len(estaciones)}")
    con = conectar()
    total_nuevos = total_act = 0
    for e in estaciones:
        obs = observaciones(cliente, e["codigoestacion"], desde)
        dias = lluvia_diaria(obs)
        registros = []
        for dia, d in sorted(dias.items()):
            registros.append({
                "fuente": FUENTE,
                "tipo": "clima",
                "url": f"{URL_API}?codigoestacion={e['codigoestacion']}",
                "titulo": e["nombreestacion"],
                "contenido": f"Precipitación acumulada del día {dia} ({e['municipio']})",
                "variable": "precipitacion_diaria_mm",
                "valor": round(d["mm"], 2),
                "unidad": "mm",
                "ts_dato": dia,
                "lat": float(e["latitud"]),
                "lon": float(e["longitud"]),
                "extra_json": {
                    "codigoestacion": e["codigoestacion"],
                    "n_observaciones": d["n"],
                    "intervalo_min": d["intervalo_min"],
                    "cobertura_dia": round(d["cobertura"], 3),
                    "max_intervalo_mm": d["max_mm"],
                    "distancia_tunja_km": round(e["km"], 2),
                },
                "hash_contenido": hash_contenido(FUENTE, e["codigoestacion"], dia, "precipitacion_diaria_mm"),
            })
        nuevos, act = guardar(con, registros, actualizar=True)
        total_nuevos += nuevos
        total_act += act
        lluvia = sum(d["mm"] for d in dias.values())
        print(f"  {e['codigoestacion']} {e['municipio']:<14} {e['km']:5.1f} km  "
              f"{len(obs):6d} obs  {len(dias):3d} días  {lluvia:7.1f} mm  "
              f"(nuevos {nuevos}, actualizados {act})")
    filas = con.execute("SELECT COUNT(*) FROM fuentes_externas WHERE tipo = 'clima'").fetchone()[0]
    print(f"Listo. Nuevos: {total_nuevos}, actualizados: {total_act}. Filas de clima en la base: {filas}")


if __name__ == "__main__":
    main()
