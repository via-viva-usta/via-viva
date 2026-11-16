"""Export de phyphox SINTÉTICO para practicar y mostrar la app en cualquier PC, sin iPhone ni datos de campo.

    viaviva capture --replay ejemplo --por-http      captura de práctica (da vueltas; eventos marcados como simulados)
    viaviva doctor --simulado ejemplo                doctor contra un phyphox simulado
    (en la app: panel de conexión → «Usar el ejemplo»)

Recorre una ruta REAL de Tunja (`web/datos/ruta_ejemplo.json`, 5,75 km por calles de OpenStreetMap desde la Plaza de
Bolívar): 8 s quieto, arranca, va entre 15 y 29 km/h con frenadas en las esquinas, pasa por huecos, resaltos y tapas
(golpes que el detector reconoce) y vuelve a parar. Se genera una vez en `data/raw/ejemplo/` (ignorado por Git).
No es un resultado: los baches están puestos a mano para que la demostración tenga algo que mostrar.
"""
from __future__ import annotations

import bisect
import json
import math
import random
from pathlib import Path

from viaviva import config

NOMBRE = "ejemplo"
VERSION = "4"                                    # sube si cambia el recorrido: se regenera solo
CARPETA = config.RAIZ / "data" / "raw" / "ejemplo" / "SINTETICO_ejemplo_phyphox"
RUTA = Path(__file__).resolve().parent / "web" / "datos" / "ruta_ejemplo.json"
G = 9.81
# (metro de la ruta, tipo): un bache cada ~350 m, de tres tipos con firmas distintas
BACHES = [(m, ("hueco", "resalto", "tapa", "hueco", "hueco", "resalto", "tapa")[k % 7])
          for k, m in enumerate(range(260, 5600, 340))]


def _metros(ruta: list[list[float]]) -> list[float]:
    k = math.cos(math.radians(ruta[0][0]))
    acum = [0.0]
    for (a, b), (c, d) in zip(ruta, ruta[1:]):
        acum.append(acum[-1] + math.hypot((c - a) * 110_574, (d - b) * 110_574 * k))
    return acum


def _punto(ruta, acum, s: float) -> tuple[float, float, float]:
    """lat, lon y rumbo (°) a s metros del inicio."""
    i = max(1, min(len(acum) - 1, bisect.bisect_right(acum, s)))
    a, b = ruta[i - 1], ruta[i]
    tramo = max(acum[i] - acum[i - 1], 1e-6)
    f = min(1.0, max(0.0, (s - acum[i - 1]) / tramo))
    rumbo = math.degrees(math.atan2((b[1] - a[1]) * math.cos(math.radians(a[0])), b[0] - a[0])) % 360
    return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, rumbo


def _perfil(largo: float, fs: float, rnd: random.Random) -> list[float]:
    """Distancia recorrida en cada muestra: quieto, arranque, crucero variable, frenadas en esquinas, parada."""
    quieto = 8.0
    dt = 1.0 / fs
    esquinas = sorted(rnd.uniform(400, largo - 300) for _ in range(6))
    s, v, t, salida = 0.0, 0.0, 0.0, []
    crucero = 6.5
    while s < largo:
        if t < quieto:
            v = 0.0
        else:
            if rnd.random() < dt / 20:                 # cada ~20 s cambia el ritmo (15–29 km/h)
                crucero = rnd.uniform(4.2, 8.0)
            objetivo = crucero
            proxima = next((e for e in esquinas if e > s), None)
            if proxima is not None and proxima - s < 35:
                objetivo = 2.5                         # frena antes de la esquina
            if largo - s < 40:
                objetivo = max(0.8, (largo - s) / 12)
            a = 1.2 if objetivo > v else -1.8
            v = min(objetivo, v + a * dt) if a > 0 else max(objetivo, v + a * dt)
        s += v * dt
        t += dt
        salida.append(min(s, largo))
    salida += [largo] * int(quieto * fs)
    return salida


# Firma de cada bache, muestra a muestra a 100 Hz (m/s² extra en el eje vertical). Bordes bruscos, como un golpe
# real: así el detector lo ve desde la primera muestra y la severidad cambia con el tipo y la velocidad.
FIRMAS = {"hueco": {0: 24.0, 1: -9.0, 2: 12.0, 3: -4.0, 5: 2.0},          # golpe seco y rebote: severidad alta
          "resalto": {0: 12.0, 1: 14.0, 2: 10.0, 3: 4.0, 5: -6.0, 6: -3.0},  # sube y baja: media
          "tapa": {0: 6.0, 1: -3.0, 2: 1.0}}                                 # golpecito: baja


def generar(carpeta: Path | None = None, fs: float = 100.0) -> Path:
    """Escribe Accelerometer.csv, Gyroscope.csv, Location.csv y meta/time.csv con los encabezados de phyphox iOS."""
    carpeta = Path(carpeta or CARPETA)
    (carpeta / "meta").mkdir(parents=True, exist_ok=True)
    ruta = json.loads(RUTA.read_text(encoding="utf-8"))["puntos"]
    acum = _metros(ruta)
    largo = acum[-1]
    rnd = random.Random(11)
    s_de = _perfil(largo, fs, rnd)
    n = len(s_de)
    vel = [0.0] + [(s_de[i] - s_de[i - 1]) * fs for i in range(1, n)]
    # cuándo pasa por cada bache
    pasos = []
    for m, tipo in BACHES:
        i = bisect.bisect_left(s_de, m)
        if i < n:
            pasos.append((i, tipo))
    with open(carpeta / "Accelerometer.csv", "w", encoding="utf-8") as f:
        f.write('"Time (s)","X (m/s^2)","Y (m/s^2)","Z (m/s^2)"\n')
        j = 0
        for i in range(n):
            t, v = i / fs, vel[i]
            ruido = 0.04 + 0.11 * min(v, 8.5) / 8.5                       # la vía vibra más con velocidad
            cuerpo = 0.25 * min(v, 8) / 8 * math.sin(2 * math.pi * 1.6 * t + 0.3 * math.sin(0.2 * t))
            extra = 0.0
            while j < len(pasos) and pasos[j][0] < i - 20:
                j += 1
            for ip, tipo in pasos[j:j + 2]:
                extra += FIRMAS[tipo].get(i - ip, 0.0) * max(0.6, min(1.4, v / 6.0))
            long = (vel[min(i + 1, n - 1)] - v) * fs if i < n - 1 else 0.0
            f.write(f"{t:.3f},{rnd.gauss(0, ruido * 0.6) + long * 0.15:.4f},{rnd.gauss(0, ruido * 0.6):.4f},"
                    f"{G + rnd.gauss(0, ruido * G * 0.1) + cuerpo + extra:.4f}\n")
    rumbos = [_punto(ruta, acum, s)[2] for s in s_de[::int(fs)]]
    with open(carpeta / "Gyroscope.csv", "w", encoding="utf-8") as f:
        f.write('"Time (s)","X (rad/s)","Y (rad/s)","Z (rad/s)"\n')
        for i in range(n):
            k = min(len(rumbos) - 1, int(i / fs))
            giro = math.radians(((rumbos[min(k + 1, len(rumbos) - 1)] - rumbos[k] + 180) % 360) - 180)
            f.write(f"{i / fs:.3f},{rnd.gauss(0, 0.01):.4f},{rnd.gauss(0, 0.01):.4f},"
                    f"{giro + rnd.gauss(0, 0.01):.4f}\n")
    with open(carpeta / "Location.csv", "w", encoding="utf-8") as f:
        f.write('"Time (s)","Latitude (°)","Longitude (°)","Height (m)","Velocity (m/s)","Direction (°)",'
                '"Horizontal Accuracy (m)","Vertical Accuracy (°)"\n')
        for k in range(int(n / fs)):
            i = int(k * fs)
            lat, lon, rumbo = _punto(ruta, acum, s_de[i])
            f.write(f"{k},{lat + rnd.gauss(0, 0.000012):.6f},{lon + rnd.gauss(0, 0.000012):.6f},"
                    f"{2810 + 8 * math.sin(s_de[i] / 900):.1f},{vel[i]:.2f},{rumbo:.0f},{rnd.uniform(3, 6):.1f},3\n")
    (carpeta / "meta" / "time.csv").write_text(
        '"event","experiment time","system time","system time text"\n"START",0,1794054000.0,"SINTETICO"\n',
        encoding="utf-8")
    (carpeta / "LEEME.txt").write_text(
        f"SINTÉTICO (versión {VERSION}): generado por viaviva.ejemplo para practicar y mostrar la app. No es un "
        f"dato real. Ruta: {largo / 1000:.2f} km por calles de Tunja (OpenStreetMap, ODbL); "
        f"{len(pasos)} baches puestos a mano.\n", encoding="utf-8")
    return carpeta


def _vigente(carpeta: Path) -> bool:
    leeme = carpeta / "LEEME.txt"
    return (carpeta / "Location.csv").exists() and leeme.exists() and \
        f"(versión {VERSION})" in leeme.read_text(encoding="utf-8")


def resolver(valor: str | None) -> str | None:
    """Si el usuario escribió «ejemplo», devuelve la ruta del export sintético (lo crea o lo actualiza)."""
    if valor is None or valor.strip().lower() != NOMBRE:
        return valor
    if not _vigente(CARPETA):
        print(f"Creando el recorrido de práctica SINTÉTICO en {CARPETA} …", flush=True)
        generar(CARPETA)
    return str(CARPETA)
