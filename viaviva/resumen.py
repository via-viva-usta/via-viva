"""RESUMEN.md de una sesión (o de un export de phyphox): duración, muestras, pérdidas, marcas por clase, km,
velocidad máxima y avisos del protocolo (≤ 30 km/h, 1 min quieto al inicio y al final, destellos para el video).

    python -m viaviva resumen <carpeta de sesión o export .zip>
Todo sale de los archivos de la sesión; nada se estima a mano.
"""
from __future__ import annotations

import csv
import json
import math
import sqlite3
import statistics
from datetime import datetime
from pathlib import Path

from viaviva import config
from viaviva.estructuras import distancia_m
from viaviva.fuentes import _leer_tabla

QUIETO_MAX_KMH = 5.0     # tolerancia: el GPS marca 3–5 km/h con el carro detenido
QUIETO_MAX_G = 0.05        # desviación de |a| (g) con el carro quieto (igual criterio que herramientas.validar_campo)
SALTO_GPS_MAX_M = 100.0    # un salto mayor entre dos fijaciones seguidas se descarta (error de GPS)


def _etiquetas(carpeta: Path) -> list[tuple[float, str]]:
    db = carpeta / "sesion.sqlite" if carpeta.is_dir() else None
    if db and db.exists():
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            return [(t, c) for t, c in con.execute("SELECT t_s, clase FROM etiquetas WHERE anulada = 0 ORDER BY t_s")]
        finally:
            con.close()
    hermano = carpeta.parent / f"{carpeta.stem}_etiquetas.csv"
    if hermano.exists():
        with open(hermano, encoding="utf-8-sig") as f:
            return [(float(r["t_s"]), r["clase"]) for r in csv.DictReader(f)]
    return []


def _bitacora(carpeta: Path) -> list[dict]:
    ruta = carpeta / "bitacora.jsonl" if carpeta.is_dir() else None
    if not ruta or not ruta.exists():
        return []
    salida = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        try:
            salida.append(json.loads(linea))
        except json.JSONDecodeError:
            pass
    return salida


def _tramo_quieto(gps, acc, desde_inicio: bool) -> float:
    """Segundos seguidos de carro quieto desde el inicio (o hacia atrás desde el final): desviación ACUMULADA de
    |a| < 0,05 g (mismo criterio de herramientas.validar_campo) y, si el GPS da velocidad válida, < 2 km/h.
    Se ignoran los primeros/últimos 5 s (tocar la pantalla para iniciar o detener mueve el celular)."""
    if not acc:
        return 0.0
    t_ini, t_fin = acc[0][0], acc[-1][0]
    vel = {int(f[0]): f[4] * 3.6 for f in gps if len(f) > 4 and not math.isnan(f[4]) and f[4] >= 0}
    mags: dict[int, list[float]] = {}
    for t, x, y, z, *_ in acc:
        mags.setdefault(int(t), []).append(math.sqrt(x * x + y * y + z * z) / 9.81)
    segundos = range(int(t_ini) + 5, int(t_fin) - 5) if desde_inicio else range(int(t_fin) - 5, int(t_ini) + 5, -1)
    quieto, acumulado = 0, []
    for s in segundos:                         # desviación acumulada (como validar_campo sobre todo el minuto)
        m = mags.get(s, [])
        if len(m) < 10 or vel.get(s, 0.0) >= QUIETO_MAX_KMH:
            break
        acumulado += m
        if statistics.pstdev(acumulado) >= QUIETO_MAX_G:
            break
        quieto += 1
    return float(quieto + 5 if quieto else 0)


def calcular(carpeta: Path) -> dict:
    carpeta = Path(carpeta)
    acc = [f for f in _leer_tabla(carpeta, "Accelerometer.csv") if len(f) >= 4 and not math.isnan(f[0])]
    gps = [f for f in _leer_tabla(carpeta, "Location.csv") if len(f) >= 3 and not math.isnan(f[0])]
    r: dict = {"carpeta": carpeta.name, "generado": datetime.now().astimezone().isoformat(timespec="seconds")}
    if len(acc) < 2:
        r["avisos"] = ["Sin datos del acelerómetro."]
        return r
    dts = [b[0] - a[0] for a, b in zip(acc, acc[1:])]
    fs = 1.0 / statistics.median([d for d in dts if d > 0])
    cortes = [d for d in dts if d > 1.5 / fs]
    r.update({"duracion_s": round(acc[-1][0] - acc[0][0], 1), "muestras": len(acc), "fs_hz": round(fs, 1),
              "cortes": len(cortes), "s_perdidos": round(sum(d - 1.0 / fs for d in cortes), 2),
              "pct_perdido": round(100 * sum(d - 1.0 / fs for d in cortes) / max(1e-9, acc[-1][0] - acc[0][0]), 2)})
    fijos = [f for f in gps if not (math.isnan(f[1]) or math.isnan(f[2]))
             and (len(f) < 7 or math.isnan(f[6]) or f[6] <= 30)]
    km = 0.0
    for a, b in zip(fijos, fijos[1:]):
        d = distancia_m(a[1], a[2], b[1], b[2])
        if d <= SALTO_GPS_MAX_M:
            km += d / 1000
    vels = [f[4] * 3.6 for f in gps if len(f) > 4 and not math.isnan(f[4]) and f[4] >= 0]
    sobre = sum(1 for v in vels if v > config.VEL_MAX_KMH)
    r.update({"puntos_gps": len(gps), "pct_gps_valido": round(100 * len(fijos) / max(1, len(gps)), 1),
              "km": round(km, 2), "vel_max_kmh": round(max(vels), 1) if vels else None,
              "pct_sobre_30_kmh": round(100 * sobre / max(1, len(vels)), 1),
              "quieto_inicio_s": round(_tramo_quieto(gps, acc, True), 1),
              "quieto_fin_s": round(_tramo_quieto(gps, acc, False), 1)})
    etq = _etiquetas(carpeta)
    por_clase: dict[str, int] = {}
    for _, c in etq:
        por_clase[c] = por_clase.get(c, 0) + 1
    bit = _bitacora(carpeta)
    destellos = _leer_tabla(carpeta, "destellos.csv") if carpeta.is_dir() else []
    eventos = _leer_tabla(carpeta, "eventos.csv") if carpeta.is_dir() else []
    r.update({"marcas": len(etq), "marcas_por_clase": dict(sorted(por_clase.items())), "destellos": len(destellos),
              "eventos_detectados": len(eventos),
              "reconexiones": sum(1 for b in bit if b.get("tipo") == "reconexion"),
              "deshechas": sum(1 for b in bit if b.get("tipo") == "deshacer")})
    avisos = []
    if r["quieto_inicio_s"] < config.QUIETO_INICIO_FIN_S - 5:
        avisos.append(f"Falta el minuto quieto al INICIO (hubo {r['quieto_inicio_s']:.0f} s).")
    if r["quieto_fin_s"] < config.QUIETO_INICIO_FIN_S - 5:
        avisos.append(f"Falta el minuto quieto al FINAL (hubo {r['quieto_fin_s']:.0f} s).")
    if r["vel_max_kmh"] is not None and r["vel_max_kmh"] > config.VEL_MAX_KMH:
        avisos.append(f"Velocidad máxima {r['vel_max_kmh']} km/h > {config.VEL_MAX_KMH:.0f} km/h "
                      f"({r['pct_sobre_30_kmh']} % del tiempo).")
    if r["pct_perdido"] > 1:
        avisos.append(f"Se perdió el {r['pct_perdido']} % de las muestras ({r['cortes']} cortes).")
    if r["pct_gps_valido"] < 80:
        avisos.append(f"GPS válido solo el {r['pct_gps_valido']} % del tiempo.")
    if carpeta.is_dir() and (carpeta / "bitacora.jsonl").exists() and r["destellos"] < 2:
        avisos.append("Menos de 2 destellos de sincronía (inicio y fin): el video será difícil de alinear.")
    if not etq:
        avisos.append("Sin marcas de etiquetado.")
    r["avisos"] = avisos
    return r


def markdown(r: dict) -> str:
    if "muestras" not in r:
        return f"# RESUMEN — {r['carpeta']}\n\n" + "\n".join(f"- {a}" for a in r.get("avisos", [])) + "\n"
    m, s = divmod(int(r["duracion_s"]), 60)
    filas = [("Duración", f"{m} min {s} s"), ("Muestras del acelerómetro", f"{r['muestras']:,}".replace(",", " ")),
             ("Frecuencia", f"{r['fs_hz']} Hz"),
             ("Pérdidas", f"{r['cortes']} cortes · {r['s_perdidos']} s ({r['pct_perdido']} %)"),
             ("Reconexiones", r["reconexiones"]), ("GPS válido", f"{r['pct_gps_valido']} % de {r['puntos_gps']} puntos"),
             ("Distancia", f"{r['km']} km"), ("Velocidad máxima", f"{r['vel_max_kmh']} km/h"),
             ("Quieto al inicio / al final", f"{r['quieto_inicio_s']} s / {r['quieto_fin_s']} s"),
             ("Marcas", f"{r['marcas']} (deshechas: {r['deshechas']})"), ("Destellos (video)", r["destellos"]),
             ("Eventos del detector", r["eventos_detectados"])]
    texto = [f"# RESUMEN — {r['carpeta']}", "", f"Generado {r['generado']} por `viaviva resumen`.", "",
             "| Dato | Valor |", "|---|---|"] + [f"| {a} | {b} |" for a, b in filas]
    texto += ["", "## Marcas por clase", ""]
    texto += ([f"- {c}: {n}" for c, n in r["marcas_por_clase"].items()] or ["- (ninguna)"])
    texto += ["", "## Avisos", ""] + ([f"- ⚠ {a}" for a in r["avisos"]] or ["- Ninguno: la sesión cumple el protocolo."])
    return "\n".join(texto) + "\n"


def generar(carpeta: Path) -> dict:
    carpeta = Path(carpeta)
    r = calcular(carpeta)
    destino = carpeta if carpeta.is_dir() else carpeta.parent
    nombre = "RESUMEN.md" if carpeta.is_dir() else f"{carpeta.stem}_RESUMEN.md"
    (destino / nombre).write_text(markdown(r), encoding="utf-8")
    if carpeta.is_dir():
        (carpeta / "resumen.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return r
