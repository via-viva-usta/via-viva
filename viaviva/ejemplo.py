"""Export de phyphox SINTÉTICO para practicar en cualquier PC, sin iPhone ni datos de campo.

    viaviva capture --replay ejemplo --por-http      captura de práctica (los eventos quedan como simulados)
    viaviva doctor --simulado ejemplo                doctor contra un phyphox simulado

Se genera una sola vez en `data/raw/ejemplo/` (ignorado por Git): 1 min quieto, 1 min a 18 km/h por una calle de Tunja
con 6 golpes, 1 min quieto. No es un resultado: sirve para ver que la instalación funciona.
"""
from __future__ import annotations

import random
from pathlib import Path

from viaviva import config

NOMBRE = "ejemplo"
CARPETA = config.RAIZ / "data" / "raw" / "ejemplo" / "SINTETICO_ejemplo_phyphox"


def generar(carpeta: Path | None = None, fs: float = 100.0) -> Path:
    """Escribe Accelerometer.csv, Gyroscope.csv, Location.csv y meta/time.csv con los encabezados de phyphox iOS."""
    carpeta = Path(carpeta or CARPETA)
    (carpeta / "meta").mkdir(parents=True, exist_ok=True)
    rnd = random.Random(11)
    quieto, rodando = 60.0, 60.0
    total = 2 * quieto + rodando
    golpes = [quieto + 8.0 + 9.0 * k for k in range(6)]

    def vel(t: float) -> float:
        return 5.0 if quieto <= t < quieto + rodando else 0.0

    n = int(total * fs)
    with open(carpeta / "Accelerometer.csv", "w", encoding="utf-8") as f:
        f.write('"Time (s)","X (m/s^2)","Y (m/s^2)","Z (m/s^2)"\n')
        for i in range(n):
            t = i / fs
            ruido = 0.15 if vel(t) else 0.03
            golpe = 12.0 if any(abs(t - g) < 0.03 for g in golpes) else 0.0
            f.write(f"{t:.4f},{rnd.gauss(0, ruido):.4f},{rnd.gauss(0, ruido):.4f},"
                    f"{9.81 + rnd.gauss(0, ruido) + golpe:.4f}\n")
    with open(carpeta / "Gyroscope.csv", "w", encoding="utf-8") as f:
        f.write('"Time (s)","X (rad/s)","Y (rad/s)","Z (rad/s)"\n')
        for i in range(n):
            f.write(f"{i / fs:.4f},{rnd.gauss(0, 0.01):.4f},{rnd.gauss(0, 0.01):.4f},{rnd.gauss(0, 0.01):.4f}\n")
    with open(carpeta / "Location.csv", "w", encoding="utf-8") as f:
        f.write('"Time (s)","Latitude (°)","Longitude (°)","Height (m)","Velocity (m/s)","Direction (°)",'
                '"Horizontal Accuracy (m)","Vertical Accuracy (°)"\n')
        lon = -73.3650
        for s in range(int(total)):
            f.write(f"{s},5.5350,{lon:.6f},2800,{vel(s):.1f},90,4,3\n")
            lon += vel(s) * 0.000009          # ~1 m ≈ 0,000009° de longitud en Tunja
    (carpeta / "meta" / "time.csv").write_text(
        '"event","experiment time","system time","system time text"\n"START",0,1794054000.0,"SINTETICO"\n',
        encoding="utf-8")
    (carpeta / "LEEME.txt").write_text("SINTÉTICO: generado por viaviva.ejemplo para practicar. No es un dato real.\n",
                                       encoding="utf-8")
    return carpeta


def resolver(valor: str | None) -> str | None:
    """Si el usuario escribió «ejemplo», devuelve la ruta del export sintético (lo crea la primera vez)."""
    if valor is None or valor.strip().lower() != NOMBRE:
        return valor
    if not (CARPETA / "Location.csv").exists():
        print(f"Creando el export de práctica SINTÉTICO en {CARPETA} …", flush=True)
        generar(CARPETA)
    return str(CARPETA)
