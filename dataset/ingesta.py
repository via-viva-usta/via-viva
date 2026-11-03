"""Ingesta del dataset de fotos tomadas con el celular → fotos difuminadas + metadatos.csv + reporte de calidad.

Entrada:  data/raw/fotos/AAAA-MM-DD_nombre/**/*.jpg|jpeg|heic   (una carpeta por persona y día; protocolo en
          docs/protocolo_fotos.md). Opcional: data/raw/nodo/**/ambiente_NNN.csv (microSD del nodo).
Salida:   data/procesado/fotos/<id>.jpg   copia SIN EXIF, enderezada, ≤ 2048 px, con caras y placas difuminadas
          data/procesado/metadatos.csv    esquema de dataset/comun.py (COLUMNAS)
          data/procesado/calidad.csv      columnas técnicas (origen, hashes, nitidez, duplicados, difuminados)
          data/procesado/reporte_calidad.md
Todo en data/ (ignorada por Git): las fotos no se suben.

Qué llena solo (las columnas que llena una persona —clase, severidad, ángulo, luz, mojado...— NUNCA se pisan):
  * fecha, hora (hora local de Colombia) y momento_dia desde el EXIF; lat, lon desde el GPS del EXIF.
  * id_tramo (tramo de OSM más cercano a ≤ 30 m) y barrio (el del tramo, o el punto de barrio más cercano).
  * tipo_via sugerido desde OSM si está vacío (la persona lo corrige en el etiquetador).
  * temperatura y humedad, en este orden: (0) si ya tiene fuente_clima = termohigrometro (anotado a mano) se deja;
    (1) registro del NODO (ambiente_NNN.csv) a ± 30 min → fuente_clima = nodo; (2) API meteorológica histórica
    gratuita por hora para Tunja (Open-Meteo, CC BY 4.0) → fuente_clima = api; lux solo si hay nodo con BH1750.
  * lluvia_ideam: precipitación diaria (mm) de la estación IDEAM más cercana con dato ese día (tabla
    fuentes_externas de la base; se actualiza con etl.scraping.clima_ideam).
  * id = primeros 12 caracteres del SHA-1 del archivo: la misma foto siempre tiene el mismo id.

Uso (desde via-viva/):
  dataset\\.venv\\Scripts\\python -m dataset.ingesta
  dataset\\.venv\\Scripts\\python -m dataset.ingesta --sin-api          (sin internet)
  dataset\\.venv\\Scripts\\python -m dataset.ingesta --sintetico        (prueba: data/raw/fotos_sintetico → data/procesado_sintetico)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import requests
from PIL import Image, ImageOps

from dataset.comun import (CLASES, COLUMNAS, COLUMNAS_CALIDAD, COLUMNAS_HUMANAS, CRUDAS, CRUDAS_SINTETICO, DATA,
                           DHASH_CASI_IGUAL, LUCES, MOMENTOS, META_POR_CLASE, META_TOTAL, NODO, PROCESADO,
                           PROCESADO_SINTETICO, RAIZ, TIPOS_VIA, TUNJA, UMBRAL_NITIDEZ, ZONA_LOCAL, ANGULOS,
                           autor_de_carpeta, distancia_m, guardar_csv, leer_metadatos, momento_dia, sitios)

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC = True
except ImportError:          # sin pillow-heif las HEIC se reportan y se saltan
    HEIC = False

EXTENSIONES = {".jpg", ".jpeg", ".heic", ".heif"}
LADO_MAX = 2048
MAX_DIST_TRAMO_M = 30.0
VENTANA_NODO_MIN = 30
CACHE_API = DATA / "raw" / "clima_api"
URL_ARCHIVO = "https://archive-api.open-meteo.com/v1/archive"
URL_PRONOSTICO = "https://api.open-meteo.com/v1/forecast"     # tiene los últimos ~90 días; el archivo va ~5 días atrás

# OSM highway → tipo de vía del dataset (sugerencia)
OSM_A_TIPO = {"trunk": "arterial", "trunk_link": "arterial", "primary": "arterial", "primary_link": "arterial",
              "secondary": "colectora", "secondary_link": "colectora", "tertiary": "colectora",
              "tertiary_link": "colectora", "residential": "local", "living_street": "local", "service": "local",
              "unclassified": "local", "track": "destapada"}


# ---------------------------------------------------------------- EXIF
def _racional(v) -> float:
    try:
        return float(v)
    except TypeError:
        return v[0] / v[1] if v[1] else 0.0


def _grados(dms, ref) -> float | None:
    try:
        g = _racional(dms[0]) + _racional(dms[1]) / 60 + _racional(dms[2]) / 3600
    except (TypeError, IndexError, ZeroDivisionError):
        return None
    return -g if ref in ("S", "W", b"S", b"W") else g


def leer_exif(img: Image.Image) -> dict:
    """Fecha y hora (con zona), y GPS. Los celulares guardan la hora LOCAL; si no hay OffsetTimeOriginal
    se asume la hora de Colombia (UTC-5)."""
    ex = img.getexif()
    sub = ex.get_ifd(0x8769)                  # Exif IFD
    gps = ex.get_ifd(0x8825)                  # GPS IFD
    texto = sub.get(36867) or ex.get(306)     # DateTimeOriginal, o DateTime
    t = None
    if texto:
        try:
            t = datetime.strptime(str(texto).strip("\x00 ")[:19], "%Y:%m:%d %H:%M:%S")
            offset = sub.get(36881)           # OffsetTimeOriginal, p. ej. '-05:00'
            m = re.match(r"([+-])(\d\d):(\d\d)", str(offset or ""))
            zona = timezone((1 if m.group(1) == "+" else -1) * timedelta(hours=int(m.group(2)),
                                                                          minutes=int(m.group(3)))) if m else ZONA_LOCAL
            t = t.replace(tzinfo=zona)
        except ValueError:
            t = None
    lat = lon = None
    if gps.get(2) and gps.get(4):
        lat, lon = _grados(gps[2], gps.get(1)), _grados(gps[4], gps.get(3))
        if lat is not None and abs(lat) < 1e-6 and abs(lon or 0) < 1e-6:   # 0,0 = el celular no tenía señal
            lat = lon = None
    return {"t": t, "lat": lat, "lon": lon}


# ---------------------------------------------------------------- calidad y privacidad
def nitidez(gris: np.ndarray) -> float:
    """Varianza del laplaciano con la imagen llevada a 1024 px de lado mayor (comparable entre celulares)."""
    f = 1024 / max(gris.shape)
    g = cv2.resize(gris, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1 else gris
    return float(cv2.Laplacian(g, cv2.CV_64F).var())


def dhash(gris: np.ndarray) -> int:
    p = cv2.resize(gris, (9, 8), interpolation=cv2.INTER_AREA)
    bits = (p[:, 1:] > p[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


_CASCADAS = None


def _cascadas():
    global _CASCADAS
    if _CASCADAS is None:
        base = Path(cv2.data.haarcascades)
        _CASCADAS = {k: cv2.CascadeClassifier(str(base / f)) for k, f in [
            ("frente", "haarcascade_frontalface_default.xml"), ("perfil", "haarcascade_profileface.xml"),
            ("placa", "haarcascade_russian_plate_number.xml")]}
    return _CASCADAS


def _fraccion(mascara: np.ndarray, r, f: float) -> float:
    x, y, w, h = [int(round(v / f)) for v in r]
    sub = mascara[y:y + h, x:x + w]
    return float((sub > 0).mean()) if sub.size else 0.0


def difuminar(bgr: np.ndarray) -> tuple[np.ndarray, int, int]:
    """Difumina caras y placas detectadas (cascadas de Haar de OpenCV). Devuelve (imagen, n_caras, n_placas).

    Es un filtro AUTOMÁTICO y puede fallar (sobre todo con placas colombianas amarillas o caras de lado):
    por eso el protocolo pide encuadrar sin personas ni placas, y el etiquetador permite excluir la foto.
    """
    gris = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    f = 1024 / max(gris.shape)
    peq = cv2.equalizeHist(cv2.resize(gris, None, fx=f, fy=f, interpolation=cv2.INTER_AREA))
    lado_min = int(0.03 * min(peq.shape))
    c = _cascadas()
    caras = [*c["frente"].detectMultiScale(peq, 1.1, 6, minSize=(lado_min, lado_min)),
             *c["perfil"].detectMultiScale(peq, 1.1, 6, minSize=(lado_min, lado_min))]
    # Las cascadas de caras "ven" caras en las franjas de la cebra y en el agregado del asfalto: se exige que al
    # menos el 15 % del recuadro tenga tono de piel (YCrCb). Sin esto se borraban justo los pasos peatonales.
    piel = cv2.inRange(cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb), (0, 133, 77), (255, 173, 127))
    caras = [r for r in caras if _fraccion(piel, r, f) >= 0.15]
    placas = list(c["placa"].detectMultiScale(peq, 1.1, 5, minSize=(2 * lado_min, lado_min)))
    out = bgr.copy()
    for (x, y, w, h) in caras + placas:
        x, y, w, h = [int(round(v / f)) for v in (x, y, w, h)]
        m = int(0.2 * max(w, h))                     # margen del 20 %
        x0, y0 = max(0, x - m), max(0, y - m)
        x1, y1 = min(out.shape[1], x + w + m), min(out.shape[0], y + h + m)
        roi = out[y0:y1, x0:x1]
        if roi.size:
            k = max(31, (max(roi.shape[:2]) // 3) | 1)
            out[y0:y1, x0:x1] = cv2.GaussianBlur(roi, (k, k), 0)
    return out, len(caras), len(placas)


# ---------------------------------------------------------------- tramos, barrios e IDEAM (desde la base)
class Base:
    """Lee tramos, barrios y lluvia IDEAM de la base SQLite. Si no existe, todo queda vacío (con aviso)."""

    def __init__(self, ruta: Path):
        self.ok = ruta.exists()
        self.seg = None
        if not self.ok:
            print(f"AVISO: no existe {ruta}: id_tramo, barrio, tipo_via y lluvia_ideam quedan vacíos")
            return
        con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
        t = pd.read_sql("SELECT id_tramo, tipo_via, barrio, geometria_wkt FROM tramos", con)
        self.barrios = pd.read_sql("SELECT nombre, lat, lon FROM barrios", con)
        self.lluvia = pd.read_sql("SELECT ts_dato, valor, lat, lon FROM fuentes_externas "
                                  "WHERE variable = 'precipitacion_diaria_mm'", con)
        con.close()
        self.info = t.set_index("id_tramo")[["tipo_via", "barrio"]]
        # Todos los segmentos de todas las líneas, en metros locales (equirrectangular alrededor de Tunja)
        filas = []
        for idt, wkt in zip(t["id_tramo"], t["geometria_wkt"]):
            pts = [tuple(map(float, p.split())) for p in re.sub(r"^LINESTRING\s*\(|\)$", "", wkt).split(",")]
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                filas.append((idt, x1, y1, x2, y2))
        s = np.array(filas)
        self.seg_id = s[:, 0].astype(int)
        self.seg = np.column_stack([*self._metros(s[:, 1], s[:, 2]), *self._metros(s[:, 3], s[:, 4])])

    @staticmethod
    def _metros(lon, lat):
        kx = 111320 * math.cos(math.radians(TUNJA[0]))
        return (np.asarray(lon) - TUNJA[1]) * kx, (np.asarray(lat) - TUNJA[0]) * 110540

    def tramo(self, lat, lon) -> tuple[str, str, str]:
        """(id_tramo, barrio, tipo_via sugerido) del tramo más cercano a ≤ MAX_DIST_TRAMO_M."""
        if not self.ok or lat is None:
            return "", "", ""
        px, py = self._metros(lon, lat)
        x1, y1, x2, y2 = self.seg.T
        dx, dy = x2 - x1, y2 - y1
        l2 = np.maximum(dx * dx + dy * dy, 1e-9)
        u = np.clip(((px - x1) * dx + (py - y1) * dy) / l2, 0, 1)
        d = np.hypot(x1 + u * dx - px, y1 + u * dy - py)
        k = int(np.argmin(d))
        if d[k] > MAX_DIST_TRAMO_M:
            return "", self.barrio_cercano(lat, lon), ""
        idt = int(self.seg_id[k])
        tipo_osm, barrio = self.info.loc[idt, "tipo_via"], self.info.loc[idt, "barrio"]
        tipo = OSM_A_TIPO.get(str(tipo_osm).split(";")[0], "otra") if pd.notna(tipo_osm) else ""
        return str(idt), (barrio if pd.notna(barrio) else self.barrio_cercano(lat, lon)), tipo

    def barrio_cercano(self, lat, lon) -> str:
        if not self.ok or self.barrios.empty:
            return ""
        d = [distancia_m(lat, lon, a, b) for a, b in zip(self.barrios["lat"], self.barrios["lon"])]
        return str(self.barrios["nombre"].iloc[int(np.argmin(d))])

    def lluvia_dia(self, fecha: str, lat, lon) -> str:
        if not self.ok or not fecha:
            return ""
        dia = self.lluvia[self.lluvia["ts_dato"].str[:10] == fecha]
        if dia.empty:
            return ""
        la, lo = (lat, lon) if lat is not None else TUNJA
        d = [distancia_m(la, lo, a, b) for a, b in zip(dia["lat"], dia["lon"])]
        return f"{float(dia['valor'].iloc[int(np.argmin(d))]):.1f}"


# ---------------------------------------------------------------- clima: nodo y API
def leer_nodo(carpeta: Path) -> pd.DataFrame:
    """Une todos los ambiente_NNN.csv; la hora UTC de cada lectura = utc_fix + ms_desde_fix."""
    partes = []
    for p in sorted(carpeta.rglob("ambiente_*.csv")):
        try:
            d = pd.read_csv(p)
        except (pd.errors.EmptyDataError, pd.errors.ParserError):
            continue
        d = d[d["utc_fix"].astype(str).str.match(r"20[2-9]\d-")]      # sin hora GPS o año 2000 = inválida
        if d.empty:
            continue
        d["t"] = pd.to_datetime(d["utc_fix"], utc=True, errors="coerce") + pd.to_timedelta(d["ms_desde_fix"], unit="ms")
        partes.append(d)
    if not partes:
        return pd.DataFrame(columns=["t", "temperatura_c", "humedad_pct", "lux", "lat", "lon", "gps_valido"])
    return pd.concat(partes, ignore_index=True).dropna(subset=["t"]).sort_values("t")


def clima_nodo(nodo: pd.DataFrame, t_utc: datetime) -> dict | None:
    if nodo.empty:
        return None
    v = nodo[(nodo["t"] - pd.Timestamp(t_utc)).abs() <= pd.Timedelta(minutes=VENTANA_NODO_MIN)]
    v = v.dropna(subset=["temperatura_c"])
    if v.empty:
        return None
    hum = v["humedad_pct"].median()
    lux = v["lux"].median() if "lux" in v and v["lux"].notna().any() else None
    return {"temperatura": f"{v['temperatura_c'].median():.1f}",
            "humedad": "" if pd.isna(hum) else f"{hum:.0f}",
            "lux": "" if lux is None or pd.isna(lux) else f"{lux:.0f}"}


def clima_api(fecha: str, hora: int) -> dict | None:
    """Temperatura a 2 m y humedad relativa por hora en el centro de Tunja (Open-Meteo, sin clave).
    Guarda cada día en data/raw/clima_api/ para no repetir consultas."""
    CACHE_API.mkdir(parents=True, exist_ok=True)
    cache = CACHE_API / f"{fecha}.json"
    datos = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else None
    if datos is None:
        params = {"latitude": TUNJA[0], "longitude": TUNJA[1], "start_date": fecha, "end_date": fecha,
                  "hourly": "temperature_2m,relative_humidity_2m", "timezone": "America/Bogota"}
        for url in (URL_ARCHIVO, URL_PRONOSTICO):
            try:
                r = requests.get(url, params=params, timeout=20)
                if r.ok:
                    h = r.json().get("hourly", {})
                    if any(v is not None for v in h.get("temperature_2m", [])):
                        datos = {"fuente": url, "hourly": h}
                        break
            except requests.RequestException:
                pass
            time.sleep(0.3)
        if datos is None:
            return None
        hoy = datetime.now(ZONA_LOCAL).date().isoformat()
        if fecha < hoy:                       # el día de hoy no se guarda: todavía le faltan horas
            cache.write_text(json.dumps(datos), encoding="utf-8")
    h = datos["hourly"]
    try:
        k = h["time"].index(f"{fecha}T{hora:02d}:00")
    except ValueError:
        return None
    t, hu = h["temperature_2m"][k], h["relative_humidity_2m"][k]
    if t is None:
        return None
    return {"temperatura": f"{t:.1f}", "humedad": "" if hu is None else f"{hu:.0f}", "lux": ""}


# ---------------------------------------------------------------- ingesta
def fotos_en(carpeta: Path) -> list[Path]:
    return sorted(p for p in carpeta.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONES)


def procesar_foto(p: Path, carpeta: Path, dir_fotos: Path, forzar: bool) -> tuple[dict, dict] | None:
    datos = p.read_bytes()
    sha = hashlib.sha1(datos).hexdigest()
    id_ = sha[:12]
    try:
        img = Image.open(p)
        ex = leer_exif(img)
        img = ImageOps.exif_transpose(img).convert("RGB")      # endereza según la orientación del celular
    except Exception as e:                                     # archivo dañado o HEIC sin pillow-heif
        print(f"  NO SE PUDO ABRIR {p.relative_to(carpeta)}: {e}")
        return None
    f = LADO_MAX / max(img.size)
    if f < 1:
        img = img.resize((round(img.width * f), round(img.height * f)), Image.LANCZOS)
    bgr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    gris = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    destino = dir_fotos / f"{id_}.jpg"
    caras = placas = 0
    if forzar or not destino.exists():
        limpia, caras, placas = difuminar(bgr)
        cv2.imwrite(str(destino), limpia, [cv2.IMWRITE_JPEG_QUALITY, 90])   # cv2 no copia el EXIF: sale sin GPS
    nit = nitidez(gris)
    rel = p.relative_to(carpeta)
    t = ex["t"]
    cal = {"id": id_, "origen": rel.as_posix(), "sha1": sha, "dhash": f"{dhash(gris):016x}",
           "ancho_px": img.width, "alto_px": img.height, "nitidez": round(nit, 1),
           "borrosa": int(nit < UMBRAL_NITIDEZ), "sin_gps": int(ex["lat"] is None), "sin_fecha": int(t is None),
           "duplicado_de": "", "caras": caras, "placas": placas,
           "utc": t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if t else ""}
    local = t.astimezone(ZONA_LOCAL) if t else None
    meta = {"id": id_, "archivo": f"fotos/{id_}.jpg", "autor": autor_de_carpeta(rel.parts[0]),
            "fecha": local.strftime("%Y-%m-%d") if local else "", "hora": local.strftime("%H:%M:%S") if local else "",
            "momento_dia": momento_dia(local.hour) if local else "",
            "lat": f"{ex['lat']:.6f}" if ex["lat"] is not None else "",
            "lon": f"{ex['lon']:.6f}" if ex["lon"] is not None else ""}
    return meta, cal


def marcar_duplicados(cal: pd.DataFrame, autor: pd.Series) -> pd.DataFrame:
    """Casi iguales: dHash a ≤ DHASH_CASI_IGUAL bits, MISMO autor y ≤ 2 min de diferencia (disparos seguidos).
    Solo con el dHash, fotos distintas de asfalto liso (vía buena) o de noche salían como duplicadas."""
    h = [int(x, 16) for x in cal["dhash"]]
    t = pd.to_datetime(cal["utc"], errors="coerce")
    dup = [""] * len(h)
    for i in range(len(h)):
        if dup[i]:
            continue
        for j in range(i + 1, len(h)):
            if dup[j] or autor.iloc[i] != autor.iloc[j] or bin(h[i] ^ h[j]).count("1") > DHASH_CASI_IGUAL:
                continue
            if pd.isna(t.iloc[i]) or pd.isna(t.iloc[j]) or abs((t.iloc[i] - t.iloc[j]).total_seconds()) <= 120:
                dup[j] = cal["id"].iloc[i]
    cal = cal.copy()
    cal["duplicado_de"] = dup
    return cal


def conteo(df: pd.DataFrame, col: str, valores: list[str]) -> list[tuple[str, int]]:
    c = df[col].replace("", "(vacío)").value_counts()
    return [(v, int(c.get(v, 0))) for v in valores] + [(k, int(n)) for k, n in c.items() if k not in valores]


def reporte(meta: pd.DataFrame, cal: pd.DataFrame, salida: Path, sintetico: bool, avisos: list[str]) -> str:
    n = len(meta)
    excluidas = meta["notas"].str.contains("EXCLUIR")
    etiq = meta[(meta["clase"] != "") & ~excluidas]
    l = [f"# Reporte de calidad del dataset de fotos{' — SINTÉTICO (solo prueba del flujo)' if sintetico else ''}", "",
         f"Generado: {datetime.now(ZONA_LOCAL):%Y-%m-%d %H:%M} (hora de Colombia) por `dataset/ingesta.py`.", "",
         "## Resumen", "",
         "| Qué | Cantidad |", "|---|---|",
         f"| Fotos | **{n}** (meta ≥ {META_TOTAL}) |",
         f"| Etiquetadas (con clase) | {len(etiq)} |",
         f"| Excluidas en el etiquetador (privacidad o foto mala) | {int(excluidas.sum())} |",
         f"| Sitios (fotos del mismo punto agrupadas) | {meta['sitio'].nunique() if n else 0} |",
         f"| Sin GPS | {int(cal['sin_gps'].sum())} |", f"| Sin fecha | {int(cal['sin_fecha'].sum())} |",
         f"| Borrosas (nitidez < {UMBRAL_NITIDEZ:g}) | {int(cal['borrosa'].sum())} |",
         f"| Casi duplicadas | {int((cal['duplicado_de'] != '').sum())} |",
         f"| Con caras / placas difuminadas (automático, revisar) | {int((cal['caras'] > 0).sum())} / {int((cal['placas'] > 0).sum())} |",
         f"| Sin tramo (a > {MAX_DIST_TRAMO_M:g} m de una calle de OSM) | {int(((meta['id_tramo'] == '') & (meta['lat'] != '')).sum())} |",
         f"| Con temperatura (nodo / termohigrómetro / API) | {int((meta['fuente_clima'] == 'nodo').sum())} / "
         f"{int((meta['fuente_clima'] == 'termohigrometro').sum())} / {int((meta['fuente_clima'] == 'api').sum())} |",
         f"| Con lluvia IDEAM del día | {int((meta['lluvia_ideam'] != '').sum())} |", ""]
    if avisos:
        l += ["**Avisos:**", ""] + [f"- {a}" for a in avisos] + [""]
    l += ["## Por clase (solo etiquetadas) y qué falta para ≥ 50", "", "| Clase | Fotos | Sitios | Faltan |", "|---|---|---|---|"]
    for c in CLASES:
        sub = etiq[etiq["clase"] == c]
        l.append(f"| {c} | {len(sub)} | {sub['sitio'].nunique()} | {max(0, META_POR_CLASE - len(sub))} |")
    falta = sum(max(0, META_POR_CLASE - int((etiq['clase'] == c).sum())) for c in CLASES)
    l += ["", f"Total que falta para llegar a {META_POR_CLASE} por clase: **{falta}** fotos etiquetadas.", ""]
    for col, vals, titulo in [("momento_dia", MOMENTOS, "momento del día"), ("luz", LUCES, "luz"),
                              ("tipo_via", TIPOS_VIA, "tipo de vía"), ("angulo", ANGULOS, "ángulo"),
                              ("superficie_mojada", ["si", "no"], "superficie mojada")]:
        l += [f"## Por {titulo}", "", "| Valor | Fotos |", "|---|---|"]
        l += [f"| {v} | {k} |" for v, k in conteo(meta, col, vals)] + [""]
    l += ["## Fotos para revisar", ""]
    for nombre, mascara in [("Sin GPS", cal["sin_gps"] == 1), ("Sin fecha", cal["sin_fecha"] == 1),
                            ("Borrosas", cal["borrosa"] == 1), ("Casi duplicadas", cal["duplicado_de"] != ""),
                            ("Con difuminado automático", (cal["caras"] > 0) | (cal["placas"] > 0))]:
        sub = cal[mascara]
        l.append(f"- **{nombre}** ({len(sub)}): " + (", ".join(f"`{o}`" for o in sub["origen"].head(30)) or "ninguna")
                 + (" …" if len(sub) > 30 else ""))
    texto = "\n".join(l) + "\n"
    (salida / "reporte_calidad.md").write_text(texto, encoding="utf-8")
    return texto


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--carpeta", type=Path, default=None, help="fotos crudas (por defecto data/raw/fotos)")
    ap.add_argument("--salida", type=Path, default=None, help="por defecto data/procesado")
    ap.add_argument("--nodo", type=Path, default=NODO, help="carpeta con ambiente_NNN.csv del nodo")
    ap.add_argument("--base", type=Path, default=DATA / "via_viva.db")
    ap.add_argument("--sin-api", action="store_true", help="no consultar la API meteorológica")
    ap.add_argument("--forzar", action="store_true", help="rehacer las fotos procesadas aunque ya existan")
    ap.add_argument("--sintetico", action="store_true", help="usar data/raw/fotos_sintetico → data/procesado_sintetico")
    a = ap.parse_args()
    carpeta = a.carpeta or (CRUDAS_SINTETICO if a.sintetico else CRUDAS)
    salida = a.salida or (PROCESADO_SINTETICO if a.sintetico else PROCESADO)
    if not a.sintetico and "sintetico" in str(carpeta).lower():
        sys.exit("Las fotos sintéticas se ingieren con --sintetico (van a data/procesado_sintetico, nunca a data/procesado)")
    if not carpeta.exists():
        sys.exit(f"No existe {carpeta}. Copiar ahí las carpetas AAAA-MM-DD_nombre de Drive (docs/protocolo_fotos.md).")
    dir_fotos = salida / "fotos"
    dir_fotos.mkdir(parents=True, exist_ok=True)
    avisos = []
    if not HEIC:
        avisos.append("pillow-heif no está instalado: las fotos HEIC no se pudieron abrir")

    rutas = fotos_en(carpeta)
    print(f"{len(rutas)} fotos en {carpeta}")
    metas, cals, vistos = [], [], set()
    for i, p in enumerate(rutas, 1):
        r = procesar_foto(p, carpeta, dir_fotos, a.forzar)
        if r is None:
            continue
        m, c = r
        if m["id"] in vistos:
            avisos.append(f"`{c['origen']}` es copia exacta de otra foto (mismo SHA-1): se ignoró")
            continue
        vistos.add(m["id"])
        metas.append(m)
        cals.append(c)
        if i % 50 == 0:
            print(f"  {i}/{len(rutas)}")
    if not metas:
        sys.exit("No se pudo leer ninguna foto")
    nuevo = pd.DataFrame(metas)
    cal = marcar_duplicados(pd.DataFrame(cals, columns=COLUMNAS_CALIDAD), nuevo["autor"])

    # Une con lo que ya había: lo que llenó una persona se conserva
    viejo = leer_metadatos(salida / "metadatos.csv").set_index("id")
    meta = nuevo.set_index("id").reindex(columns=[c for c in COLUMNAS if c != "id"]).fillna("")
    for idx in meta.index.intersection(viejo.index):
        for col in COLUMNAS_HUMANAS + ["temperatura", "humedad", "lux", "fuente_clima"]:
            meta.loc[idx, col] = viejo.loc[idx, col]
    meta = meta.reset_index()

    # La lectura del termohigrómetro se escribe en UNA foto del punto (protocolo): se copia a las demás del sitio
    sitio = sitios(meta)
    termo = meta[(meta["fuente_clima"] == "termohigrometro") & (meta["temperatura"] != "")]
    lectura = {sitio[k]: (r["temperatura"], r["humedad"]) for k, r in termo.iterrows()}
    for k in meta.index:
        if sitio[k] in lectura and meta.at[k, "fuente_clima"] != "termohigrometro":
            meta.at[k, "temperatura"], meta.at[k, "humedad"] = lectura[sitio[k]]
            meta.at[k, "fuente_clima"], meta.at[k, "lux"] = "termohigrometro", ""

    base = Base(a.base)
    nodo = leer_nodo(a.nodo) if a.nodo.exists() else leer_nodo(Path("__no_existe__"))
    if nodo.empty:
        avisos.append(f"No hay registros del nodo (ambiente_NNN.csv) en {a.nodo}: temperatura y humedad desde la API")
    sin_api = 0
    for k, r in meta.iterrows():
        lat = float(r["lat"]) if r["lat"] else None
        lon = float(r["lon"]) if r["lon"] else None
        idt, barrio, tipo = base.tramo(lat, lon)
        meta.at[k, "id_tramo"], meta.at[k, "barrio"] = idt, barrio
        if not r["tipo_via"] and tipo:
            meta.at[k, "tipo_via"] = tipo
        meta.at[k, "lluvia_ideam"] = base.lluvia_dia(r["fecha"], lat, lon)
        if r["fuente_clima"] == "termohigrometro" or not r["fecha"]:
            continue                               # anotado a mano, o sin fecha no hay cómo cruzar
        t_local = datetime.strptime(f"{r['fecha']} {r['hora']}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZONA_LOCAL)
        c = clima_nodo(nodo, t_local.astimezone(timezone.utc))
        fuente = "nodo"
        if c is None and not a.sin_api:
            hora = (t_local + timedelta(minutes=30)).replace(minute=0, second=0)   # hora redonda más cercana
            c = clima_api(hora.strftime("%Y-%m-%d"), hora.hour)
            fuente = "api"
            sin_api += c is None
        if c is not None:
            meta.at[k, "temperatura"], meta.at[k, "humedad"] = c["temperatura"], c["humedad"]
            meta.at[k, "lux"], meta.at[k, "fuente_clima"] = c["lux"], fuente
    if sin_api:
        avisos.append(f"{sin_api} fotos sin dato de la API meteorológica (¿sin internet o fecha futura?)")
    if a.sintetico:
        meta["notas"] = meta["notas"].where(meta["notas"].str.contains("SINTETICO"), ("SINTETICO " + meta["notas"]).str.strip())

    meta = meta.sort_values(["fecha", "hora", "id"]).reset_index(drop=True)
    guardar_csv(meta[COLUMNAS], salida / "metadatos.csv")
    guardar_csv(cal, salida / "calidad.csv")
    meta["sitio"] = sitios(meta).to_numpy()
    cal = cal.set_index("id").loc[meta["id"]].reset_index()
    texto = reporte(meta, cal, salida, a.sintetico, avisos)
    print(texto)
    print(f"Escrito {salida / 'metadatos.csv'} ({len(meta)} fotos), calidad.csv y reporte_calidad.md")


if __name__ == "__main__":
    main()
