"""Ingesta de sesiones REALES al dataset de VÍA VIVA, fuera de Git, con procedencia y aptitud explícitas.

    python -m herramientas.ingestar_sesion agregar <carpeta_sesion> [--destino C:\\VIA_VIVA_DATOS\\dataset_vv]
    python -m herramientas.ingestar_sesion indice  [--destino …]     (tabla de sesiones y por qué no son aptas)
    python -m herramientas.ingestar_sesion aptas   [--destino …]     (rutas listas para `viaviva dataset construir`)

- El original NO se toca: se copia tal cual a `<destino>/sesiones/<nombre>/` (más `<nombre>_etiquetas.csv` al lado,
  como en 06_CAMPO; sin el video, que solo se referencia). Procedencia (SHA-256 de cada archivo), auditoría y
  correcciones van en `<destino>/meta/<nombre>/`. Así `viaviva dataset construir <destino>/sesiones` lee la copia.
- Rechaza sesiones grabadas desde una reproducción (`origen: simulado`) o con nombre SINTÉTICO: el dataset es solo de
  registros reales. Rechaza un destino dentro del repositorio o de 06_CAMPO.
- Corre `herramientas/auditar_sesion.py` sobre la copia. Si la hora de la fuente está desfasada, guarda la corrección en
  `correcciones.json` (no reescribe la copia): quien consuma `ts_utc`/`utc` debe restarla.
- `apto_entrenamiento` es falso mientras falte algo: auditoría con FALLA (salvo la hora ya documentada), video sin
  sincronía por destello, marcas sin revisar con video o fuente sin rol/alias registrado. Los motivos quedan escritos.
  No se completan ni inventan etiquetas.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from herramientas import auditar_sesion

REPO = Path(__file__).resolve().parent.parent
DESTINO = Path(r"C:\VIA_VIVA_DATOS\dataset_vv") if sys.platform == "win32" else Path.home() / "VIA_VIVA_DATOS" / "dataset_vv"
VIDEO = (".mp4", ".mov", ".webm", ".m4v")
CAMPOS_INDICE = ["sesion", "origen", "id_nodo", "dur_s", "marcas", "revisadas", "video", "hora_corr_s", "apto", "motivos"]


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _dentro(p: Path, base: Path) -> bool:
    try:
        p.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _bitacora(c: Path) -> list[dict]:
    if not (c / "bitacora.jsonl").exists():
        return []
    return [json.loads(x) for x in (c / "bitacora.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]


def agregar(origen: Path, destino: Path = DESTINO) -> dict:
    origen, destino = Path(origen), Path(destino)
    if not (origen / "Accelerometer.csv").exists():
        raise ValueError(f"{origen.name}: no es una carpeta de sesión (falta Accelerometer.csv)")
    if _dentro(destino, REPO) or _dentro(destino, REPO.parent.parent / "06_CAMPO") or _dentro(destino, origen):
        raise ValueError("El destino no puede estar dentro del repositorio, de 06_CAMPO ni de la sesión")
    bit = _bitacora(origen)
    inicio = next((b for b in bit if b.get("tipo") == "inicio"), {})
    if "SINTETICO" in origen.name.upper() or inicio.get("origen") == "simulado":
        raise ValueError(f"{origen.name}: sesión de reproducción o SINTÉTICA; el dataset solo admite registros reales")
    crudo = destino / "sesiones" / origen.name
    final = destino / "meta" / origen.name
    if crudo.exists() or final.exists():
        raise ValueError(f"{origen.name} ya está en el dataset ({crudo}); bórrela a mano si quiere volver a ingestarla")
    crudo.mkdir(parents=True)
    final.mkdir(parents=True)
    archivos, videos = {}, []
    for p in sorted(origen.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(origen).as_posix()
        if p.suffix.lower() in VIDEO:
            videos.append({"archivo": rel, "bytes": p.stat().st_size, "ruta_original": str(p)})
            continue
        (crudo / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, crudo / rel)
        archivos[rel] = _sha(p)
    vig = origen.parent / f"{origen.name}_etiquetas.csv"
    if vig.exists():
        shutil.copy2(vig, crudo.parent / vig.name)
        archivos["../" + vig.name] = _sha(vig)
    # copia verificada
    for rel, h in archivos.items():
        copia = crudo.parent / vig.name if rel.startswith("../") else crudo / rel
        if _sha(copia) != h:
            raise OSError(f"La copia de {rel} no coincide con el original")
    # auditoría sobre la copia (sus marcas vigentes quedaron al lado, como en 06_CAMPO)
    inf = auditar_sesion.auditar(crudo)
    (final / "auditoria.json").write_text(json.dumps({"items": inf.items, "datos": inf.datos}, ensure_ascii=False,
                                                     indent=1), encoding="utf-8")
    # marcas revisadas con video (tabla revision de la base de la sesión)
    revisadas = 0
    if (crudo / "sesion.sqlite").exists():
        con = sqlite3.connect(f"file:{(crudo / 'sesion.sqlite').as_posix()}?mode=ro", uri=True)
        try:
            revisadas = con.execute("SELECT COUNT(*) FROM revision").fetchone()[0]
        except sqlite3.Error:
            revisadas = 0
        con.close()
    marcas = inf.datos.get("marcas", {}).get("vigentes", 0)
    video = json.loads((crudo / "video.json").read_text(encoding="utf-8")) if (crudo / "video.json").exists() else {}
    hora = inf.datos.get("hora_fuente_menos_pc_s")
    fuente = inicio.get("fuente") if isinstance(inicio.get("fuente"), dict) else None
    dispositivos = ([fuente] if fuente and fuente.get("alias", "desconocido") != "desconocido" else []) + [
        b for b in bit if b.get("tipo") == "dispositivo"]
    motivos = []
    fallas = [q for e, q, _ in inf.items if e == "FALLA" and "desfasad" not in q and "corrido" not in q]
    if fallas:
        motivos.append("auditoría con FALLA: " + "; ".join(fallas))
    if hora is not None and abs(hora) > 2:
        motivos.append(f"hora de la fuente desfasada {hora:+.1f} s (corrección en correcciones.json, sin aplicar)")
    if not video:
        motivos.append("sin video para revisar las marcas")
    elif video.get("metodo") != "destello":
        motivos.append(f"video sincronizado por «{video.get('metodo')}», no por destello")
    if marcas == 0:
        motivos.append("sin marcas")
    elif revisadas < marcas:
        motivos.append(f"marcas revisadas con video: {revisadas} de {marcas}")
    if not dispositivos:
        motivos.append("sin rol/alias de dispositivo registrado (identidad física desconocida)")
    proc = {
        "sesion": origen.name, "ingestado": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ruta_original": str(origen), "origen": inicio.get("origen", "desconocido"),
        "id_nodo": inicio.get("id_nodo", "desconocido"), "fs_hz": inicio.get("fs_hz"),
        "dispositivos": [{k: d.get(k) for k in ("rol", "alias", "fuente", "agente")} for d in dispositivos] or "desconocido",
        "duracion_s": inf.datos.get("sensores", {}).get("Accelerometer.csv", {}).get("dur_s"),
        "marcas_vigentes": marcas, "marcas_revisadas": revisadas,
        "video": {k: video.get(k) for k in ("archivo", "metodo", "desfase_s", "duracion_s")} if video else None,
        "videos_no_copiados": videos, "sha256": archivos,
        "apto_entrenamiento": not motivos, "motivos_no_apto": motivos,
        "nota": "Copia de un registro real. No se completaron ni modificaron etiquetas.",
    }
    (final / "procedencia.json").write_text(json.dumps(proc, ensure_ascii=False, indent=1), encoding="utf-8")
    if hora is not None and abs(hora) > 2:
        (final / "correcciones.json").write_text(json.dumps({
            "restar_a_ts_utc_y_utc_s": round(hora, 3),
            "evidencia": "meta/time.csv (hora de la fuente) frente a la bitácora (reloj del equipo); ver auditoria.json",
            "aplicada": False}, ensure_ascii=False, indent=1), encoding="utf-8")
    _escribir_indice(destino)
    return proc


def _escribir_indice(destino: Path) -> list[dict]:
    filas = []
    for p in sorted((destino / "meta").glob("*/procedencia.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        corr = p.parent / "correcciones.json"
        filas.append({"sesion": d["sesion"], "origen": d["origen"], "id_nodo": d["id_nodo"], "dur_s": d["duracion_s"],
                      "marcas": d["marcas_vigentes"], "revisadas": d["marcas_revisadas"],
                      "video": (d["video"] or {}).get("metodo"),
                      "hora_corr_s": json.loads(corr.read_text(encoding="utf-8"))["restar_a_ts_utc_y_utc_s"]
                      if corr.exists() else 0, "apto": d["apto_entrenamiento"],
                      "motivos": " | ".join(d["motivos_no_apto"])})
    if filas:
        with open(destino / "indice.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CAMPOS_INDICE)
            w.writeheader()
            w.writerows(filas)
    return filas


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("accion", choices=["agregar", "indice", "aptas"])
    ap.add_argument("carpeta", nargs="?", type=Path)
    ap.add_argument("--destino", type=Path, default=DESTINO)
    a = ap.parse_args(argv)
    if a.accion == "agregar":
        if not a.carpeta:
            ap.error("falta la carpeta de la sesión")
        try:
            p = agregar(a.carpeta, a.destino)
        except (ValueError, OSError) as err:
            print(f"No se ingestó: {err}")
            return 1
        print(json.dumps({k: p[k] for k in ("sesion", "origen", "duracion_s", "marcas_vigentes", "marcas_revisadas",
                                            "apto_entrenamiento", "motivos_no_apto")}, ensure_ascii=False, indent=1))
        return 0
    filas = _escribir_indice(a.destino) if (a.destino / "meta").exists() else []
    if a.accion == "aptas":
        for f in filas:
            if f["apto"]:
                print(a.destino / "sesiones" / f["sesion"])
        return 0
    for f in filas:
        print(f"{f['sesion']}  {f['origen']}  {f['dur_s']} s  marcas {f['revisadas']}/{f['marcas']} revisadas  "
              f"apto={f['apto']}  {f['motivos']}")
    if not filas:
        print("El dataset está vacío.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
