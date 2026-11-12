"""Flujo único del dataset dentro de la app: SESIONES → IMPORTAR VIDEO → REVISIÓN → DATASET.

- `listar` / `detalle`: cada salida con su resumen, calidad, recorrido, señal, eventos del detector y marcas.
- La subida por la API + `sincronizar_video`: el video del iPhone B se asocia a la sesión y se alinea SOLO:
    1. destellos de `/sync` vistos en el video (2 Hz blanco/negro durante 3 s) contra `destellos.csv`  → ± 1 cuadro
    2. si no se ven: fecha de creación del .mov/.mp4 contra el inicio de la sesión                      → ± 1–2 s
    3. si tampoco: desfase 0 y se ajusta a mano en la revisión.
- `revisar`: confirmar, corregir o descartar cada evento; queda en `sesion.sqlite` (tabla `revision`) y rehace
  `<carpeta>_etiquetas.csv`, que es lo que leen el detector y el dataset. Descartar = `via_buena` (falsa alarma).
- `construir_dataset`: ventanas + calidad + evaluación de umbrales, con el resultado en `ultimo.json`.
Nada sale de la carpeta de sesiones (06_CAMPO), que está fuera de Git.
"""
from __future__ import annotations

import csv
import json
import math
import re
import shutil
import sqlite3
import struct
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path

from viaviva import config, resumen
from viaviva.fuentes import _leer_tabla

NOMBRE_OK = re.compile(r"^sesion_[\w\-]+$")
VIDEOS = (".mov", ".mp4", ".m4v")
MAX_VIDEO_BYTES = 8 * 1024**3  # admite videos largos; el límite también se aplica al cuerpo transmitido
CLASES = [c for _, c, _ in config.ETIQUETAS]
SALIDA_DATASET = config.RAIZ / "data" / "procesado" / "dataset_ventanas"
HEVC = ("hvc1", "hev1", "hevc", "h265", "x265")
_tarea = {"estado": "inactivo", "mensaje": ""}
_candado_video = threading.Lock()


def carpeta(base: Path, nombre: str) -> Path:
    if not NOMBRE_OK.fullmatch(nombre or "") or not (Path(base) / nombre / "Accelerometer.csv").exists():
        raise ValueError(f"sesión desconocida: {nombre}")
    return Path(base) / nombre


def _resumen(c: Path) -> dict:
    f = c / "resumen.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return resumen.generar(c)


def _db(c: Path) -> sqlite3.Connection:
    con = sqlite3.connect(c / "sesion.sqlite")
    con.execute("CREATE TABLE IF NOT EXISTS revision (t_s REAL PRIMARY KEY, decision TEXT NOT NULL, clase TEXT, "
                "usuario TEXT, utc TEXT)")
    return con


def video_info(c: Path) -> dict | None:
    f = c / "video.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def listar(base: Path, grabando: str | None = None) -> list[dict]:
    salida = []
    for c in sorted(Path(base).glob("sesion_*"), reverse=True):
        if not c.is_dir() or not (c / "Accelerometer.csv").exists():
            continue
        if c.name == grabando:
            salida.append({"nombre": c.name, "grabando": True})
            continue
        try:
            r = _resumen(c)
            con = _db(c)
            revisados = con.execute("SELECT COUNT(*) FROM revision").fetchone()[0]
            _asegurar_etiquetas(c, con)
            con.close()
        except Exception as err:
            salida.append({"nombre": c.name, "error": str(err)})
            continue
        v = video_info(c)
        salida.append({"nombre": c.name, "grabando": False, "video": bool(v), "sincronia": (v or {}).get("metodo"),
                       "revisados": revisados,
                       **{k: r.get(k) for k in ("duracion_s", "km", "vel_max_kmh", "marcas", "eventos_detectados",
                                                "pct_perdido", "pct_gps_valido", "avisos", "marcas_por_clase")}})
    return salida


def detalle(c: Path) -> dict:
    """Todo lo que la revisión necesita, ya reducido (envolvente a 10 Hz, recorrido a 1 Hz)."""
    from viaviva import detector
    from viaviva.senal import cargar
    s = cargar(c)
    n = int(s.fs / 10)
    env = [[round(float(s.t[i]), 1), round(float(max(abs(s.a_v[i:i + n].min()), abs(s.a_v[i:i + n].max()))), 3)]
           for i in range(0, len(s.t) - n, n)]
    paso = int(s.fs)
    tray = [[round(float(s.lat[i]), 6), round(float(s.lon[i]), 6)] for i in range(0, len(s.t), paso)
            if not math.isnan(s.lat[i])]
    eventos = detector.detectar(s, detector.cargar_parametros())
    con = _db(c)
    rev = {round(t, 2): {"decision": d, "clase": cl} for t, d, cl in con.execute("SELECT t_s, decision, clase FROM revision")}
    try:
        marcas = [{"t_s": t, "clase": cl} for t, cl in con.execute(
            "SELECT t_s, clase FROM etiquetas WHERE anulada = 0 ORDER BY t_s")]
    except sqlite3.OperationalError:
        marcas = []
    con.close()
    for e in eventos:
        e["revision"] = rev.get(round(e["t_s"], 2))
    destellos = [f[0] for f in _leer_tabla(c, "destellos.csv")]
    return {"nombre": c.name, "resumen": _resumen(c), "duracion_s": round(float(s.t[-1]), 1), "envolvente": env,
            "trayecto": tray, "eventos": eventos, "marcas": marcas, "destellos": destellos, "video": video_info(c),
            "clases": CLASES, "revisados": len(rev), "ffmpeg": ffmpeg() is not None}


# ------------------------------------------------------------------------------------------------ video
def _creacion_mov(ruta: Path) -> float | None:
    """Fecha de creación (epoch UTC) del átomo `mvhd` de un .mov/.mp4 (segundos desde 1904). None si no está."""
    try:
        with open(ruta, "rb") as f:
            fin = ruta.stat().st_size
            pos = 0
            while pos < fin:
                f.seek(pos)
                cab = f.read(8)
                if len(cab) < 8:
                    return None
                tam, tipo = struct.unpack(">I4s", cab)
                if tam == 1:
                    tam = struct.unpack(">Q", f.read(8))[0]
                if tipo == b"moov":
                    datos = f.read(min(tam, 4096))
                    i = datos.find(b"mvhd")
                    if i < 0:
                        return None
                    version = datos[i + 4]
                    t = struct.unpack(">Q" if version == 1 else ">I", datos[i + 8: i + (16 if version == 1 else 12)])[0]
                    return t - 2082844800 if t > 2082844800 else None
                if tam < 8:
                    return None
                pos += tam
    except OSError:
        return None
    return None


def _destellos_en_video(ruta: Path, tramos_s: float = 240.0) -> tuple[list[float], dict]:
    """Instantes (s del video) donde empieza un destello: ≥ 6 saltos fuertes de brillo en 3 s. Requiere OpenCV."""
    try:
        import cv2
    except ImportError:
        return [], {"error": "sin OpenCV: no se pueden buscar los destellos (se usa la fecha del archivo)"}
    cap = cv2.VideoCapture(str(ruta))
    if not cap.isOpened():
        return [], {"error": "no se pudo abrir el video"}
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    dur = total / fps if total else 0.0
    cc = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
    codec = "".join(chr((cc >> 8 * k) & 0xFF) for k in range(4)).strip("\x00 ").lower() if cc else ""
    info = {"fps": round(fps, 2), "duracion_s": round(dur, 1), "ancho": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "alto": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), "codec": codec}
    rangos = [(0.0, dur)] if dur <= 2 * tramos_s else [(0.0, tramos_s), (dur - tramos_s, dur)]
    inicios = []
    for a, b in rangos:                                   # los destellos van al inicio y al final de la toma
        cap.set(cv2.CAP_PROP_POS_MSEC, a * 1000)
        ts, brillo = [], []
        while True:
            t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
            ok, cuadro = cap.read()
            if not ok or t > b:
                break
            ts.append(t)
            brillo.append(float(cv2.resize(cuadro, (32, 18)).mean()))
        saltos = [ts[i] for i in range(1, len(brillo)) if abs(brillo[i] - brillo[i - 1]) > 45]
        i = 0
        while i < len(saltos):
            dentro = [x for x in saltos[i:] if x - saltos[i] <= 3.2]
            if len(dentro) >= 6:
                inicios.append(round(saltos[i], 3))
                i += len(dentro)
            else:
                i += 1
    cap.release()
    return inicios, info


def sincronizar_video(c: Path, ruta: Path) -> dict:
    inicio = _leer_tabla(c, "time.csv")
    inicio_epoch = inicio[0][2] if inicio and len(inicio[0]) > 2 else None
    ses = [f[0] for f in _leer_tabla(c, "destellos.csv")]
    vistos, info = _destellos_en_video(ruta)
    r = {"archivo": ruta.name, "importado": datetime.now(UTC).isoformat(timespec="seconds"), **info,
         "destellos_video": vistos, "destellos_sesion": ses, "avisos": []}
    if vistos and ses:                                    # se emparejan en orden; desfase = mediana
        pares = list(zip(ses, vistos)) if len(ses) == len(vistos) else [(ses[0], vistos[0])]
        difs = sorted(a - b for a, b in pares)
        r.update(metodo="destello", desfase_s=round(difs[len(difs) // 2], 3),
                 error_s=round(max(difs) - min(difs), 3) if len(difs) > 1 else None)
        if len(ses) != len(vistos):
            r["avisos"].append(f"{len(vistos)} destellos en el video y {len(ses)} en la sesión: se usó el primero.")
    else:
        creado = _creacion_mov(ruta)
        if creado and inicio_epoch:
            r.update(metodo="fecha_del_archivo", desfase_s=round(creado - inicio_epoch, 2), error_s=None)
            r["avisos"].append("No se vieron destellos: sincronía por la fecha del archivo (± 1–2 s). Ajústela en la "
                               "revisión si hace falta.")
        else:
            r.update(metodo="manual", desfase_s=0.0, error_s=None)
            r["avisos"].append("Sin destellos ni fecha en el archivo: ajuste el desfase a mano en la revisión.")
    if r.get("codec") in HEVC:
        r["avisos"].append("Video HEVC (formato «Alta eficiencia» del iPhone): Chrome o Edge en Windows pueden no "
                           "reproducirlo. " + ("Use «Convertir a H.264»." if ffmpeg() else
                                               "Instale ffmpeg para convertirlo o grabe en «Más compatible»."))
    dur_ses = _resumen(c).get("duracion_s") or 0
    dur_vid = r.get("duracion_s") or 0
    if dur_vid:
        cubre = max(0.0, min(dur_ses, r["desfase_s"] + dur_vid) - max(0.0, r["desfase_s"]))
        r["cobertura_pct"] = round(100 * cubre / dur_ses, 1) if dur_ses else None
        if dur_ses and cubre < 0.5 * dur_ses:
            r["avisos"].append(f"El video cubre solo el {r['cobertura_pct']} % de la sesión: ¿es el video correcto?")
    (c / "video.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    return r


def ruta_video(c: Path) -> Path | None:
    v = video_info(c)
    return (c / v["archivo"]) if v and (c / v["archivo"]).exists() else None


def ffmpeg() -> str | None:
    """Ruta de ffmpeg si está instalado (opcional: solo hace falta para convertir videos HEVC)."""
    return shutil.which("ffmpeg")


def _guardar_video_info(c: Path, **cambios) -> dict:
    with _candado_video:
        v = video_info(c) or {}
        v.update(cambios)
        (c / "video.json").write_text(json.dumps(v, ensure_ascii=False, indent=1), encoding="utf-8")
        return v


def _convertir(c: Path, origen: Path, destino: Path, exe: str) -> None:
    cmd = [exe, "-y", "-v", "error", "-i", str(origen), "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264",
           "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart",
           str(destino)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=6 * 3600)
        ok = p.returncode == 0 and destino.exists() and destino.stat().st_size > 1000
        error = "" if ok else (p.stderr or "ffmpeg terminó con error").strip().splitlines()[-1][:300]
    except (OSError, subprocess.TimeoutExpired) as e:
        ok, error = False, str(e)[:300]
    if ok:  # misma línea de tiempo: el desfase y la sincronía siguen valiendo; el original se conserva
        _guardar_video_info(c, archivo=destino.name, original=origen.name, codec="h264",
                            conversion={"estado": "lista", "fin": datetime.now(UTC).isoformat(timespec="seconds")})
    else:
        destino.unlink(missing_ok=True)
        _guardar_video_info(c, conversion={"estado": "error", "mensaje": error})


def convertir_video(c: Path) -> dict:
    """Convierte el video de la sesión a H.264/MP4 con ffmpeg, en segundo plano. No borra el original."""
    origen = ruta_video(c)
    if origen is None:
        raise ValueError("la sesión no tiene video")
    exe = ffmpeg()
    if exe is None:
        raise ValueError("ffmpeg no está instalado en este equipo")
    v = video_info(c) or {}
    if (v.get("conversion") or {}).get("estado") == "en_curso":
        return v
    destino = c / f"{origen.stem}_h264.mp4"
    v = _guardar_video_info(c, conversion={"estado": "en_curso",
                                           "inicio": datetime.now(UTC).isoformat(timespec="seconds")})
    threading.Thread(target=_convertir, args=(c, origen, destino, exe), daemon=True).start()
    return v


def ajustar_desfase(c: Path, desfase_s: float) -> dict:
    v = video_info(c)
    if not v:
        raise ValueError("la sesión no tiene video")
    return _guardar_video_info(c, desfase_s=round(float(desfase_s), 3), metodo="manual")


# ------------------------------------------------------------------------------------------------ revisión
def revisar(c: Path, t_s: float, decision: str, clase: str | None, usuario: str) -> dict:
    if decision not in ("confirmar", "corregir", "descartar", "borrar"):
        raise ValueError(f"decisión inválida: {decision}")
    if decision in ("confirmar", "corregir") and clase not in CLASES:
        raise ValueError(f"clase inválida: {clase}")
    con = _db(c)
    if decision == "borrar":
        con.execute("DELETE FROM revision WHERE t_s = ?", (round(t_s, 2),))
    else:
        con.execute("INSERT OR REPLACE INTO revision VALUES (?,?,?,?,?)",
                    (round(t_s, 2), decision, "via_buena" if decision == "descartar" else clase, usuario,
                     datetime.now(UTC).isoformat(timespec="seconds")))
    con.commit()
    n = escribir_etiquetas(c, con)
    con.close()
    return {"ok": True, "etiquetas": n}


def _asegurar_etiquetas(c: Path, con: sqlite3.Connection) -> None:
    """Una sesión copiada de otro PC (zip de la carpeta) llega sin `<carpeta>_etiquetas.csv`, que vive al lado:
    se rehace con lo que guarda `sesion.sqlite` (marcas vigentes + revisión)."""
    if not (c.parent / f"{c.name}_etiquetas.csv").exists():
        escribir_etiquetas(c, con)


def escribir_etiquetas(c: Path, con: sqlite3.Connection) -> int:
    """`<carpeta>_etiquetas.csv` = eventos revisados + marcas del copiloto que no estén a ± 1,5 s de uno revisado."""
    rev = con.execute("SELECT t_s, clase FROM revision ORDER BY t_s").fetchall()
    try:
        marcas = con.execute("SELECT t_s, clase FROM etiquetas WHERE anulada = 0").fetchall()
    except sqlite3.OperationalError:
        marcas = []
    filas = list(rev) + [(t, cl) for t, cl in marcas if all(abs(t - tr) > 1.5 for tr, _ in rev)]
    with open(c.parent / f"{c.name}_etiquetas.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "clase"])
        w.writerows((round(t, 2), cl) for t, cl in sorted(filas))
    return len(filas)


# ------------------------------------------------------------------------------------------------ dataset
def construir_dataset(base: Path) -> dict:
    """Ventanas + calidad + umbrales con TODAS las sesiones. Devuelve (y guarda) un resumen para la pantalla."""
    from collections import Counter

    from viaviva import detector, ventanas
    from viaviva.senal import cargar
    rutas = [c for c in sorted(Path(base).glob("sesion_*")) if (c / "Accelerometer.csv").exists()]
    if not rutas:
        raise ValueError("no hay sesiones grabadas")
    for c in rutas:
        if (c / "sesion.sqlite").exists():
            con = _db(c)
            _asegurar_etiquetas(c, con)
            con.close()
    salida = ventanas.construir(rutas)
    with open(salida / "manifest.csv", encoding="utf-8") as f:
        filas = list(csv.DictReader(f))
    validas = [w for w in filas if w["estado"] == "ok"]
    clases = Counter(w["etiqueta"] for w in validas if w["etiqueta"] != "sin_marca")
    p = detector.cargar_parametros()
    senales = [cargar(c) for c in rutas]
    r = {"generado": datetime.now().astimezone().isoformat(timespec="seconds"), "carpeta": str(salida),
         "sesiones": len(rutas), "ventanas": len(filas), "validas": len(validas),
         "con_marca": sum(clases.values()), "por_clase": dict(clases.most_common()),
         "cobertura_pct": round(100 * sum(clases.values()) / max(1, len(validas)), 1),
         "desbalance": round(max(clases.values()) / min(clases.values()), 1) if len(clases) > 1 else None,
         "detector": detector.evaluar(senales, p), "version_detector": p["version"]}
    val = detector.validar_dejando_una_fuera(senales, p)
    val.pop("final", None)
    r["calibracion"] = val
    try:
        r["clasificador"] = ventanas.evaluar(salida / "manifest.csv")
    except ImportError:
        r["clasificador"] = {"error": "scikit-learn no está instalado en este entorno"}
    r["avisos"] = []
    if r["con_marca"] < 30:
        r["avisos"].append(f"Solo {r['con_marca']} ventanas con marca: las cifras no son concluyentes.")
    if any("SINTETICO" in c.name.upper() or "simul" in c.name.lower() for c in rutas):
        r["avisos"].append("Hay sesiones de prueba entre los datos.")
    (SALIDA_DATASET / "ultimo.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return r


def lanzar_dataset(base: Path) -> dict:
    if _tarea["estado"] == "corriendo":
        return dict(_tarea)

    def correr():
        try:
            construir_dataset(base)
            _tarea.update(estado="listo", mensaje="")
        except Exception as err:
            _tarea.update(estado="error", mensaje=str(err))
    _tarea.update(estado="corriendo", mensaje="")
    threading.Thread(target=correr, daemon=True, name="dataset").start()
    return dict(_tarea)


def estado_dataset() -> dict:
    f = SALIDA_DATASET / "ultimo.json"
    return {**_tarea, "ultimo": json.loads(f.read_text(encoding="utf-8")) if f.exists() else None}
