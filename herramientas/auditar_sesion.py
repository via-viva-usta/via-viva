"""Auditoría de SOLO LECTURA de una carpeta de sesión de la app (PC con phyphox o Raspberry Pi): dice OK / AVISO / FALLA
con lo que hay que revisar. Sirve para la prueba de mesa antes de salir y para revisar lo que llega del campo.

    python -m herramientas.auditar_sesion <carpeta_sesion> [--json salida.json]

Revisa: cada CSV de sensor (filas, Hz, huecos, duplicados, NaN, saturación, 1 g en reposo), desfase entre
acelerómetros, GPS (1 Hz, fijación, precisión, saltos), **hora** (meta/time.csv frente a la bitácora del PC: en la
salida del 18-nov hubo +2 109 s), marcas (CSV, SQLite, vigentes, contradictorias), eventos (CSV frente a SQLite),
destellos, minuto quieto y video. No escribe nada en la carpeta y no imprime coordenadas.
Solo necesita numpy (corre en la Pi). Código de salida 1 si hay alguna FALLA.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

G = 9.81
ACELEROMETROS = {"Accelerometer.csv": "acelerómetro principal (ADXL345 #1 o phyphox)",
                 "Accelerometer_adxl2.csv": "ADXL345 #2", "Accelerometer_mpu6050.csv": "MPU-6050"}
FS_ESPERADA = {"Accelerometer.csv": None, "Accelerometer_adxl2.csv": None, "Accelerometer_mpu6050.csv": 100.0,
               "Gyroscope.csv": None}


class Informe:
    def __init__(self):
        self.items: list[tuple[str, str, str]] = []
        self.datos: dict = {}

    def ok(self, que, detalle=""):
        self.items.append(("OK", que, detalle))

    def aviso(self, que, detalle=""):
        self.items.append(("AVISO", que, detalle))

    def falla(self, que, detalle=""):
        self.items.append(("FALLA", que, detalle))

    @property
    def fallas(self) -> int:
        return sum(1 for e, _, _ in self.items if e == "FALLA")

    def texto(self) -> str:
        filas = [f"  [{e:^5}] {q}" + (f" — {d}" if d else "") for e, q, d in self.items]
        n = {e: sum(1 for x, _, _ in self.items if x == e) for e in ("OK", "AVISO", "FALLA")}
        return "\n".join(filas + [f"Resumen: {n['OK']} OK · {n['AVISO']} AVISO · {n['FALLA']} FALLA"])


def leer_csv(ruta: Path) -> tuple[list[str], np.ndarray]:
    """Encabezado y matriz float (las celdas vacías o de texto quedan NaN)."""
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.reader(f))
    if not filas:
        return [], np.empty((0, 0))
    enc, cuerpo = filas[0], filas[1:]

    def num(x):
        try:
            return float(x)
        except ValueError:
            return math.nan
    return enc, np.array([[num(x) for x in fila] for fila in cuerpo], float).reshape(len(cuerpo), len(enc))


def _utc(texto: str) -> float | None:
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def revisar_serie(nombre: str, m: np.ndarray, inf: Informe, con_nan: bool = True) -> dict | None:
    if m.shape[0] < 2:
        inf.aviso(f"{nombre}: sin datos", "si este sensor va montado, revise el cableado y `viaviva doctor --source pi`")
        return None
    t = m[:, 0]
    dt = np.diff(t)
    fs = (len(t) - 1) / (t[-1] - t[0]) if t[-1] > t[0] else math.nan
    paso = float(np.median(dt))
    huecos = dt[dt > 1.5 * paso]
    d = {"filas": int(len(t)), "fs_hz": round(fs, 2), "dur_s": round(float(t[-1] - t[0]), 1),
         "huecos": int(len(huecos)), "s_en_huecos": round(float((huecos - paso).sum()), 3),
         "duplicados": int((dt == 0).sum()), "retrocesos": int((dt < 0).sum()),
         "nan": int(np.isnan(m[:, 1:4]).sum()) if con_nan and m.shape[1] >= 4 else 0}
    problemas = [k for k in ("duplicados", "retrocesos", "nan") if d[k]]
    if problemas:
        inf.falla(f"{nombre}: {', '.join(f'{k} {d[k]}' for k in problemas)}", "datos dañados o fuente reiniciada")
    elif d["huecos"]:
        inf.aviso(f"{nombre}: {d['huecos']} huecos ({d['s_en_huecos']} s)", f"{d['fs_hz']} Hz, {d['dur_s']} s")
    else:
        inf.ok(f"{nombre}: {d['filas']} filas a {d['fs_hz']} Hz sin huecos", f"{d['dur_s']} s")
    return d


def revisar_acelerometro(nombre: str, m: np.ndarray, inf: Informe) -> np.ndarray | None:
    d = revisar_serie(nombre, m, inf)
    if d is None:
        return None
    xyz = m[:, 1:4]
    norma = np.linalg.norm(xyz, axis=1) / G
    tope = np.abs(xyz).max(axis=0)
    # saturación: el mismo valor extremo repetido, y solo en ejes que llegan a ≥ 1,5 g (en reposo no hay tope)
    en_tope = int(sum((np.abs(xyz[:, k]) >= tope[k] - 1e-6).sum() for k in range(3) if tope[k] >= 1.5 * G))
    d.update(norma_mediana_g=round(float(np.nanmedian(norma)), 3), max_abs_g=round(float(tope.max() / G), 2),
             muestras_en_tope=en_tope)
    if not 0.9 < d["norma_mediana_g"] < 1.1:
        inf.falla(f"{nombre}: la mediana de |a| es {d['norma_mediana_g']} g (debería ser ≈ 1 g)",
                  "unidades o escala mal configuradas (m/s² con gravedad)")
    if en_tope > 10:
        inf.aviso(f"{nombre}: {en_tope} muestras en el valor máximo ({d['max_abs_g']} g)", "posible saturación: suba el rango")
    inf.datos.setdefault("sensores", {})[nombre] = d
    return m


def desfase_entre(a: np.ndarray, b: np.ndarray, fs: float = 100.0, max_s: float = 0.5) -> tuple[float, float] | None:
    """Desfase (s) de b respecto de a y correlación, con |a|−1 g en una rejilla común."""
    t0, t1 = max(a[0, 0], b[0, 0]), min(a[-1, 0], b[-1, 0])
    if t1 - t0 < 10:
        return None
    t = np.arange(t0, min(t1, t0 + 300), 1 / fs)
    sa = np.interp(t, a[:, 0], np.linalg.norm(a[:, 1:4], axis=1))
    sb = np.interp(t, b[:, 0], np.linalg.norm(b[:, 1:4], axis=1))
    sa, sb = sa - sa.mean(), sb - sb.mean()
    k = int(max_s * fs)
    mejor = max(((float(np.dot(sa[k:-k], np.roll(sb, -j)[k:-k])), j) for j in range(-k, k + 1)))
    den = float(np.linalg.norm(sa[k:-k]) * np.linalg.norm(np.roll(sb, -mejor[1])[k:-k])) or 1.0
    return mejor[1] / fs, mejor[0] / den


def auditar(c: Path) -> Informe:
    inf = Informe()
    c = Path(c)
    if not (c / "Accelerometer.csv").exists():
        inf.falla("No es una carpeta de sesión", f"falta Accelerometer.csv en {c.name}")
        return inf
    inf.datos["carpeta"] = c.name
    # --- sensores
    acc = {}
    for nombre in ACELEROMETROS:
        if (c / nombre).exists():
            m = revisar_acelerometro(nombre, leer_csv(c / nombre)[1], inf)
            if m is not None:
                acc[nombre] = m
    if (c / "Gyroscope.csv").exists():
        revisar_serie("Gyroscope.csv", leer_csv(c / "Gyroscope.csv")[1], inf)
    base = acc.get("Accelerometer.csv")
    for nombre, m in acc.items():
        if nombre == "Accelerometer.csv" or base is None:
            continue
        r = desfase_entre(base, m)
        if r is None:
            continue
        lag, corr = r
        inf.datos.setdefault("entre_sensores", {})[nombre] = {"desfase_s": round(lag, 3), "correlacion": round(corr, 2)}
        if abs(lag) > 0.02 or corr < 0.5:
            inf.aviso(f"{nombre} frente al principal: desfase {lag * 1e3:+.0f} ms, r = {corr:.2f}",
                      "revise montaje (misma caja, mismos ejes) y la hora de cada lectura")
        else:
            inf.ok(f"{nombre} coincide con el principal", f"desfase {lag * 1e3:+.0f} ms, r = {corr:.2f}")
    for extra in ("Ambiente.csv", "Distancia_vl53l0x.csv"):
        if (c / extra).exists():
            n = max(0, sum(1 for _ in open(c / extra, encoding="utf-8")) - 1)
            (inf.ok if n else inf.aviso)(f"{extra}: {n} filas", "" if n else "sensor opcional sin datos")
    # --- GPS
    if (c / "Location.csv").exists():
        enc, g = leer_csv(c / "Location.csv")
        d = revisar_serie("Location.csv", g, inf, con_nan=False) if len(g) > 1 else None   # NaN = sin fijación
        if d:
            validos = ~np.isnan(g[:, 1]) & ~np.isnan(g[:, 2])
            iv = enc.index("Velocity (m/s)") if "Velocity (m/s)" in enc else None
            ip = enc.index("Horizontal Accuracy (m)") if "Horizontal Accuracy (m)" in enc else None
            gps = {"pct_valido": round(100 * float(validos.mean()), 1)}
            if iv is not None:
                gps["vel_max_kmh"] = round(float(np.nanmax(g[:, iv])) * 3.6, 1)
            if ip is not None and not np.isnan(g[:, ip]).all():
                gps["precision_mediana_m"] = round(float(np.nanmedian(g[:, ip])), 1)
            la, lo = np.radians(g[validos, 1]), np.radians(g[validos, 2])
            if len(la) > 1:
                dist = 6371000 * 2 * np.arcsin(np.sqrt(np.sin(np.diff(la) / 2) ** 2 + np.cos(la[:-1]) * np.cos(la[1:])
                                                       * np.sin(np.diff(lo) / 2) ** 2))
                v = dist / np.maximum(np.diff(g[validos, 0]), 1e-3) * 3.6
                gps["saltos_>80kmh"] = int((v > 80).sum())
                gps["km"] = round(float(dist.sum()) / 1000, 2)
            inf.datos["gps"] = gps
            if gps["pct_valido"] < 90:
                inf.aviso(f"GPS válido solo {gps['pct_valido']} %", "espere la fijación (LED/`doctor`) antes de arrancar")
            if gps.get("saltos_>80kmh"):
                inf.aviso(f"GPS: {gps['saltos_>80kmh']} saltos de posición > 80 km/h", "multitrayecto o antena tapada")
    # --- hora: meta/time.csv (hora de la fuente) frente a la bitácora (reloj del PC/Pi)
    bit = []
    if (c / "bitacora.jsonl").exists():
        bit = [json.loads(x) for x in (c / "bitacora.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    inicio = next((b for b in bit if b.get("tipo") == "inicio"), {})
    if (c / "meta" / "time.csv").exists() and inicio:
        _, meta = leer_csv(c / "meta" / "time.csv")
        start, pc = (float(meta[0, 2]) if meta.size else math.nan), _utc(inicio.get("utc"))
        if pc and not math.isnan(start):
            dif = start - pc
            inf.datos["hora_fuente_menos_pc_s"] = round(dif, 3)
            if abs(dif) > 2:
                inf.falla(f"Hora de la sesión desfasada {dif:+.1f} s respecto del reloj del equipo",
                          "ts_utc de eventos y marcas quedan corridos; reinicie la captura y revise la hora (NTP/GPS)")
            else:
                inf.ok("Hora de la sesión = reloj del equipo", f"{dif:+.2f} s")
    tipos = [b.get("tipo") for b in bit]
    for tipo, que in (("reinicio_phyphox", "reinicios de phyphox"), ("hora", "re-anclajes de hora"),
                      ("corte", "cortes de conexión"), ("perdida", "pérdidas > 0,5 s")):
        if tipos.count(tipo):
            inf.aviso(f"Bitácora: {tipos.count(tipo)} {que}")
    if bit and tipos[-1] != "fin":
        inf.falla("La bitácora no tiene «fin»", "la grabación no se cerró bien (apagón o cierre forzado)")
    # --- marcas y eventos
    etq = list(csv.DictReader(open(c / "etiquetas.csv", encoding="utf-8"))) if (c / "etiquetas.csv").exists() else []
    vig_ruta = c.parent / f"{c.name}_etiquetas.csv"
    vig = list(csv.DictReader(open(vig_ruta, encoding="utf-8"))) if vig_ruta.exists() else []
    por_clase: dict[str, int] = {}
    for x in vig:
        por_clase[x["clase"]] = por_clase.get(x["clase"], 0) + 1
    inf.datos["marcas"] = {"etiquetas_csv": len(etq), "vigentes": len(vig), "por_clase": por_clase}
    ts = sorted((float(x["t_s"]), x["clase"]) for x in vig if x.get("t_s"))
    contra = [(round(a, 2), ca, cb) for (a, ca), (b, cb) in zip(ts, ts[1:]) if b - a < 0.5 and ca != cb]
    if contra:
        inf.aviso(f"{len(contra)} pares de marcas contradictorias a < 0,5 s", f"p. ej. t = {contra[0][0]} s: "
                  f"{contra[0][1]} / {contra[0][2]}; corríjalas en Revisión")
    if etq and not vig:
        inf.falla("Hay marcas pero no el archivo de marcas vigentes", vig_ruta.name)
    ev = list(csv.DictReader(open(c / "eventos.csv", encoding="utf-8"))) if (c / "eventos.csv").exists() else []
    inf.datos["eventos"] = len(ev)
    if (c / "sesion.sqlite").exists():
        con = sqlite3.connect(f"file:{(c / 'sesion.sqlite').as_posix()}?mode=ro", uri=True)
        try:
            n_db = con.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
            n_etq = con.execute("SELECT COUNT(*) FROM etiquetas").fetchone()[0]
        except sqlite3.Error:
            n_db = n_etq = None
        con.close()
        if n_db is not None and n_db != len(ev):
            inf.aviso(f"Eventos: {len(ev)} en eventos.csv y {n_db} en sesion.sqlite", "la base tiene casi duplicados")
        if n_etq is not None and n_etq != len(etq):
            inf.falla(f"Marcas: {len(etq)} en etiquetas.csv y {n_etq} en sesion.sqlite")
    if ev:
        revisar_hora_eventos(inicio, ev, inf)
    (inf.ok if len(vig) else inf.aviso)(f"Marcas vigentes: {len(vig)}", json.dumps(por_clase, ensure_ascii=False))
    # --- destellos, quieto y video
    n_dest = max(0, sum(1 for _ in open(c / "destellos.csv", encoding="utf-8")) - 1) if (c / "destellos.csv").exists() else 0
    (inf.ok if n_dest >= 2 else inf.aviso)(f"Destellos de sincronía: {n_dest}", "" if n_dest >= 2 else
                                           "haga uno al inicio y otro al final frente a la cámara")
    if (c / "resumen.json").exists():
        r = json.loads((c / "resumen.json").read_text(encoding="utf-8"))
        for k, que in (("quieto_inicio_s", "inicio"), ("quieto_fin_s", "final")):
            if k in r:
                (inf.ok if r[k] >= 50 else inf.aviso)(f"Quieto al {que}: {r[k]} s", "" if r[k] >= 50 else "pida 1 min")
    if (c / "video.json").exists():
        v = json.loads((c / "video.json").read_text(encoding="utf-8"))
        (inf.ok if v.get("metodo") == "destello" else inf.aviso)(
            f"Video: sincronía por {v.get('metodo')}, desfase {v.get('desfase_s')} s", v.get("archivo", ""))
    return inf


def revisar_hora_eventos(inicio: dict, ev: list[dict], inf: Informe) -> None:
    """ts_utc de los eventos frente a (hora del PC al iniciar + t_s): mide el mismo desfase desde los eventos."""
    pc = _utc(inicio.get("utc")) if inicio else None
    if not pc:
        return
    difs = [(_utc(e["ts_utc"]) or math.nan) - (pc + float(e["t_s"])) for e in ev if e.get("ts_utc")]
    difs = [d for d in difs if not math.isnan(d)]
    if difs:
        med = float(np.median(difs))
        inf.datos["eventos_ts_utc_menos_pc_s"] = round(med, 2)
        if abs(med) > 2:
            inf.falla(f"ts_utc de los eventos corrido {med:+.1f} s", "no cruce estos eventos con otras fuentes por hora")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("carpeta", type=Path)
    ap.add_argument("--json", type=Path, help="guardar los datos medidos (fuera de 06_CAMPO)")
    a = ap.parse_args(argv)
    inf = auditar(a.carpeta)
    print(f"Sesión {a.carpeta.name}\n{inf.texto()}")
    if a.json:
        a.json.write_text(json.dumps({"items": inf.items, "datos": inf.datos}, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    return 1 if inf.fallas else 0


if __name__ == "__main__":
    sys.exit(main())
