"""Copia la base a data/via_viva_demo.db y le agrega eventos y reportes DEMO (marcados) para mostrar la demo
cuando todavía no hay datos reales. La base real (data/via_viva.db) NO se toca.

Marcas: eventos con origen='simulado', id_nodo='DEMO' y modelo_version='DEMO'; reportes con hash_usuario='demo' y
descripción que empieza por 'DEMO'. El tablero, el mapa y el bot los muestran con aviso.

Uso: etl\\.venv\\Scripts\\python demo\\datos_demo.py [--n 40]
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

RAIZ = Path(__file__).resolve().parent.parent
REAL = RAIZ / "data" / "via_viva.db"
DEMO = RAIZ / "data" / "via_viva_demo.db"
sys.path.insert(0, str(RAIZ))
from db.acceso import conectar  # noqa: E402
from etl.geohash import codificar  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=40, help="eventos DEMO (los reportes son n/4)")
    ap.add_argument("--semilla", type=int, default=5)
    a = ap.parse_args()
    if not REAL.exists():
        sys.exit(f"No existe {REAL}: reconstruir la base con db\\reconstruir.ps1")
    shutil.copy2(REAL, DEMO)
    con = conectar(f"sqlite:///{DEMO.as_posix()}")          # aplica migraciones (columnas nuevas de reportes)
    rng = np.random.default_rng(a.semilla)
    tramos = con.execute("SELECT id_tramo, lat_centro, lon_centro FROM tramos WHERE barrio NOT LIKE 'Vereda%' "
                         "ORDER BY RANDOM()").fetchall()
    ahora = datetime.now(timezone.utc)
    t_iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")     # noqa: E731
    with con:
        for i in range(a.n):
            idt, la, lo = tramos[i % 60]                   # 60 tramos: algunos se repiten (reincidencia)
            la, lo = la + rng.normal(0, 4e-5), lo + rng.normal(0, 4e-5)
            clase = rng.choice(["hueco", "hueco", "resalto", "impacto_fuerte", "obstaculo"])
            t = ahora - timedelta(minutes=int(rng.integers(5, 6000)))
            con.execute(
                "INSERT OR IGNORE INTO eventos (id_nodo, ts_utc, lat, lon, velocidad_kmh, clase, severidad, confianza, "
                "origen, razon_umbral, modelo_version, id_tramo, geohash7, ts_carga) "
                "VALUES ('DEMO',?,?,?,?,?,?,?,'simulado',?,'DEMO',?,?,?)",
                (t_iso(t), la, lo, float(rng.uniform(10, 30)), str(clase), float(rng.uniform(0.1, 1)),
                 float(rng.uniform(0.5, 0.95)), float(rng.uniform(6, 20)), idt, codificar(la, lo, 7), t_iso(ahora)))
        for i in range(a.n // 4):
            idt, la, lo = tramos[i]
            con.execute(
                "INSERT INTO reportes (canal, hash_usuario, ts_utc, lat, lon, tipo, descripcion, estado, ts_estado, "
                "id_tramo, geohash7, ts_carga) VALUES ('telegram','demo',?,?,?,?,?,?,?,?,?,?)",
                (t_iso(ahora - timedelta(hours=int(rng.integers(1, 72)))), la, lo,
                 str(rng.choice(["hueco", "obstaculo", "resalto"])), "DEMO: reporte de prueba",
                 str(rng.choice(["nuevo", "confirmado", "en_reparacion"])), t_iso(ahora), idt, codificar(la, lo, 7),
                 t_iso(ahora)))
    n_ev = con.execute("SELECT COUNT(*) FROM eventos WHERE origen='simulado'").fetchone()[0]
    n_rep = con.execute("SELECT COUNT(*) FROM reportes WHERE hash_usuario='demo'").fetchone()[0]
    con.close()
    print(f"Base DEMO: {DEMO} ({n_ev} eventos y {n_rep} reportes DEMO)")


if __name__ == "__main__":
    main()
