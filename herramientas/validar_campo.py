"""Revisión rápida de lo que llega del campo, ANTES de procesarlo: dice "bien" o "corregir: …" con la acción concreta.

Revisa:
  * phyphox (data/raw/phyphox/): columnas reconocidas (si no, dice exactamente cuáles vio), tasa real (Hz), huecos de
    muestreo, aceleración con g, GPS (% del tiempo con fijación y precisión), velocidad máxima, duración, 1 min quieto
    al inicio y al final, y si hay etiquetas (o vueltas sin convertir).
  * fotos (data/raw/fotos/**): carpeta AAAA-MM-DD_nombre, EXIF con fecha, hora y GPS (JPG y HEIC), resolución,
    orientación, nitidez, señales de WhatsApp, y tarjeta ArUco detectada en al menos una foto de cada punto.
  * planilla (data/raw/planilla/*.csv): filas sin fotos a ± 5 min y puntos con fotos pero sin fila.

Uso (desde via-viva/):
  dataset\\.venv\\Scripts\\python -m herramientas.validar_campo
  dataset\\.venv\\Scripts\\python -m herramientas.validar_campo --fotos data\\raw\\fotos_sintetico --phyphox data\\raw\\phyphox_sintetico
Escribe también data/raw/validacion_campo.md (ignorada por Git).
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from PIL import Image

from analysis import senales
from dataset import planilla as plan_campo
from dataset.comun import CRUDAS, DATA, PLANILLA, UMBRAL_NITIDEZ, ZONA_LOCAL, sitios
from dataset.escala import detectar
from dataset.ingesta import EXTENSIONES, HEIC, leer_exif, nitidez

PHYPHOX = DATA / "raw" / "phyphox"
G = 9.81
TASA_MIN_HZ = 80          # iPhone de Pipe: ~100 Hz
MP_MIN = 3.0              # megapíxeles: menos suele ser captura de pantalla o foto reenviada
QUIETO_MAX_G = 0.05      # |a| casi constante con el motor en ralentí; [AJUSTAR con el primer recorrido real]


class Informe:
    def __init__(self):
        self.lineas, self.bien, self.corregir = [], 0, 0

    def titulo(self, t):
        self.lineas += ["", f"## {t}", ""]

    def ok(self, t):
        self.bien += 1
        self.lineas.append(f"- BIEN: {t}")

    def mal(self, t, accion):
        self.corregir += 1
        self.lineas.append(f"- CORREGIR: {t} → {accion}")

    def info(self, t):
        self.lineas.append(f"- {t}")


# ---------------------------------------------------------------- phyphox
def entradas_phyphox(carpeta: Path) -> list[Path]:
    return [p for p in sorted(carpeta.glob("*")) if not p.name.startswith("_")
            and not re.search(r"_(etiquetas\.csv|vueltas\.txt)$", p.name)
            and (p.is_dir() or p.suffix.lower() in (".zip", ".csv"))]


def columnas_vistas(p: Path) -> str:
    try:
        return "; ".join(f"[{', '.join(map(str, t.columns))}]" for t in senales._tablas(p))
    except Exception as e:              # archivo dañado
        return f"(no se pudo leer: {e})"


def quieto(acc: pd.DataFrame, t0: float, t1: float) -> float | None:
    """Desviación de |a| (en g) en [t0, t1]; None si no hay datos."""
    v = acc[(acc["t"] >= t0) & (acc["t"] <= t1)]
    if len(v) < 20:
        return None
    return float(np.sqrt(v["ax"] ** 2 + v["ay"] ** 2 + v["az"] ** 2).std() / G)


def revisar_phyphox(p: Path, inf: Informe) -> None:
    inf.titulo(f"phyphox · {p.name}")
    try:
        d = senales.cargar_phyphox_completo(p)
    except Exception:
        inf.mal("no reconozco el acelerómetro en el export",
                f"exportar desde phyphox como CSV (coma decimal: no importa). Columnas que vi: {columnas_vistas(p)}")
        return
    acc, giro, gps = d["acc"], d["giro"], d["gps"]
    t = acc["t"].to_numpy()
    dur = float(t[-1] - t[0])
    dt = np.diff(t)
    fs = 1 / float(np.median(dt))
    inf.info(f"duración {dur / 60:.1f} min · {len(acc)} muestras · tasa real {fs:.1f} Hz")
    if fs >= TASA_MIN_HZ:
        inf.ok(f"tasa del acelerómetro {fs:.0f} Hz")
    else:
        inf.mal(f"tasa del acelerómetro {fs:.0f} Hz (< {TASA_MIN_HZ})",
                "en phyphox, al crear el experimento, poner la tasa máxima del sensor")
    huecos = dt > 5 * np.median(dt)
    perdido = float(dt[huecos].sum())
    if perdido > 0.01 * dur:
        inf.mal(f"{huecos.sum()} cortes de muestreo ({perdido:.1f} s perdidos, el mayor de {dt.max():.1f} s)",
                "pantalla siempre encendida, no cambiar de app ni bloquear el celular durante el recorrido")
    else:
        inf.ok(f"muestreo continuo ({huecos.sum()} cortes menores, {perdido:.1f} s)")
    media_g = float(np.sqrt(acc["ax"] ** 2 + acc["ay"] ** 2 + acc["az"] ** 2).mean() / G)
    if not acc.attrs.get("con_g", True) or media_g < 0.5:
        inf.mal(f"aceleración SIN gravedad (|a| medio = {media_g:.2f} g)",
                "usar el sensor 'Accelerometer' (con g), no 'Linear acceleration'")
    else:
        inf.ok(f"aceleración con gravedad (|a| medio = {media_g:.2f} g)")
    for nombre, t0, t1 in [("al inicio", t[0] + 5, t[0] + 60), ("al final", t[-1] - 60, t[-1] - 5)]:
        s = quieto(acc, t0, t1)
        if s is None:
            inf.mal(f"recorrido muy corto para revisar el minuto quieto {nombre}", "grabar ≥ 3 min")
        elif s < QUIETO_MAX_G:
            inf.ok(f"1 min quieto {nombre} (variación {s:.3f} g)")
        else:
            inf.mal(f"no hubo 1 min quieto {nombre} (variación {s:.3f} g)",
                    f"dejar el carro detenido 1 min con phyphox grabando {nombre} del recorrido")
    if giro is None:
        inf.mal("sin giroscopio", "agregar 'Gyroscope' al experimento de phyphox")
    else:
        inf.ok("giroscopio presente")
    if gps is None or len(gps) < 5:
        inf.mal("sin GPS", "agregar 'Location (GPS)' al experimento y dar a phyphox permiso de ubicación PRECISA")
    else:
        # % de los segundos del recorrido con al menos una fijación (phyphox da ~1 fijación por segundo)
        segundos = np.unique(np.floor(gps["t"].to_numpy() - t[0]).astype(int))
        pct = 100 * len(segundos[(segundos >= 0) & (segundos <= dur)]) / max(1, int(dur) + 1)
        (inf.ok if pct >= 80 else lambda x: inf.mal(x, "esperar ≥ 6 satélites antes de play; celular cerca del parabrisas"))(
            f"GPS con fijación en ~{pct:.0f} % del recorrido ({len(gps)} puntos)")
        vmax = float(np.nanmax(gps["vel"])) * 3.6 if gps["vel"].notna().any() else np.nan
        if np.isfinite(vmax):
            (inf.ok if vmax <= 35 else lambda x: inf.mal(x, "conducir a máx. 30 km/h (decisión del 2-nov)"))(
                f"velocidad máxima {vmax:.0f} km/h")
    base = p.with_suffix("") if p.suffix else p
    etq = base.parent / f"{base.name}_etiquetas.csv"
    vue = base.parent / f"{base.name}_vueltas.txt"
    if etq.exists():
        e = pd.read_csv(etq)
        fuera = e[(e["t_s"] < 0) | (e["t_s"] > dur + 5)]
        if len(fuera):
            inf.mal(f"{len(fuera)} etiquetas fuera de la duración del recorrido",
                    "revisar que el cronómetro se inició junto con phyphox y el orden de las vueltas (--invertir)")
        else:
            inf.ok(f"etiquetas: {len(e)} filas dentro del recorrido")
    elif vue.exists():
        inf.mal("hay vueltas sin convertir", f"analysis\\vueltas_a_etiquetas.py {vue}")
    else:
        inf.mal("sin etiquetas del copiloto", f"subir {base.name}_vueltas.txt (cronómetro por vueltas)")


# ---------------------------------------------------------------- fotos
def revisar_fotos(carpeta: Path, inf: Informe) -> pd.DataFrame:
    inf.titulo(f"Fotos · {carpeta}")
    rutas = sorted(p for p in carpeta.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONES)
    if not rutas:
        inf.info("no hay fotos")
        return pd.DataFrame()
    filas = []
    for p in rutas:
        rel = p.relative_to(carpeta)
        f = {"origen": rel.as_posix(), "autor": rel.parts[0], "fecha": "", "hora": "", "lat": "", "lon": "",
             "mp": 0.0, "nitidez": 0.0, "vertical": False, "tarjeta": False, "error": ""}
        try:
            img = Image.open(p)
            ex = leer_exif(img)
            from PIL import ImageOps
            img = ImageOps.exif_transpose(img).convert("RGB")
        except Exception as e:
            f["error"] = str(e)
            filas.append(f)
            continue
        if ex["t"]:
            local = ex["t"].astimezone(ZONA_LOCAL)
            f["fecha"], f["hora"] = local.strftime("%Y-%m-%d"), local.strftime("%H:%M:%S")
        if ex["lat"] is not None:
            f["lat"], f["lon"] = f"{ex['lat']:.6f}", f"{ex['lon']:.6f}"
        f["mp"] = img.width * img.height / 1e6
        f["vertical"] = img.height > img.width
        esc = 1600 / max(img.size)
        peq = img.resize((round(img.width * esc), round(img.height * esc))) if esc < 1 else img
        bgr = cv2.cvtColor(np.asarray(peq), cv2.COLOR_RGB2BGR)
        f["nitidez"] = nitidez(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
        f["tarjeta"] = bool(detectar(bgr))
        filas.append(f)
    df = pd.DataFrame(filas)
    for autor, d in df.groupby("autor"):
        if not re.match(r"^\d{4}-\d{2}-\d{2}_\w+", autor):
            inf.mal(f"carpeta `{autor}` sin el formato AAAA-MM-DD_nombre", "renombrar en Drive, p. ej. 2026-11-06_juandiego")
    malas = df[df["error"] != ""]
    if len(malas):
        accion = "instalar pillow-heif en dataset\\.venv" if not HEIC and any(
            o.lower().endswith((".heic", ".heif")) for o in malas["origen"]) else "volver a subir el archivo original"
        inf.mal(f"{len(malas)} fotos no se pudieron abrir: {', '.join(malas['origen'].head(5))}", accion)
    df = df[df["error"] == ""].copy()
    n = len(df)
    inf.info(f"{n} fotos legibles en {df['autor'].nunique()} carpetas")
    whatsapp = df[df["origen"].str.contains(r"-WA\d+|whatsapp", case=False, regex=True)]
    if len(whatsapp):
        inf.mal(f"{len(whatsapp)} fotos parecen venir de WhatsApp", "subir los ORIGINALES desde la app de Drive (WhatsApp borra el GPS)")
    for col, nombre, accion in [
            ("fecha", "fecha y hora", "fecha y hora automáticas en el celular; subir el original, no una copia"),
            ("lat", "GPS", "iPhone: Ajustes → Privacidad → Localización → Cámara: 'Mientras se usa' + Ubicación exacta")]:
        sin = df[df[col] == ""]
        if len(sin):
            inf.mal(f"{len(sin)} de {n} fotos sin {nombre} en el EXIF ({', '.join(sin['origen'].head(3))}…)", accion)
        else:
            inf.ok(f"todas las fotos tienen {nombre}")
    bajas = df[df["mp"] < MP_MIN]
    if len(bajas):
        inf.mal(f"{len(bajas)} fotos de menos de {MP_MIN:g} MP", "tomar con la cámara a 1×, sin zoom; no capturas de pantalla")
    else:
        inf.ok(f"resolución ≥ {MP_MIN:g} MP (mediana {df['mp'].median():.1f} MP)")
    vert = df[df["vertical"]]
    if len(vert) > 0.2 * n:
        inf.mal(f"{len(vert)} fotos verticales", "tomarlas en HORIZONTAL (protocolo, sección 3)")
    borr = df[df["nitidez"] < UMBRAL_NITIDEZ]
    if len(borr) > 0.1 * n:
        inf.mal(f"{len(borr)} fotos borrosas ({', '.join(borr['origen'].head(3))}…)",
                "limpiar el lente, quedarse quieto al disparar; de noche apoyar el celular")
    else:
        inf.ok(f"nitidez aceptable ({len(borr)} borrosas de {n})")
    df["sitio"] = sitios(df).to_numpy() if n else []
    sin_tarjeta = [s for s, d in df.groupby("sitio") if not d["tarjeta"].any()]
    inf.info(f"{df['sitio'].nunique()} puntos (sitios); tarjeta ArUco detectada en {int(df['tarjeta'].sum())} fotos")
    if sin_tarjeta:
        ej = df[df["sitio"].isin(sin_tarjeta)].groupby("sitio")["origen"].first().head(5)
        inf.mal(f"{len(sin_tarjeta)} puntos sin la tarjeta en ninguna foto (p. ej. {', '.join(ej)})",
                "en la foto cenital: tarjeta plana, completa, junto al daño, sin sombra encima, celular paralelo al piso")
    else:
        inf.ok("todos los puntos tienen la tarjeta en alguna foto")
    return df


# ---------------------------------------------------------------- planilla
def revisar_planilla(carpeta: Path, fotos: pd.DataFrame, inf: Informe) -> None:
    inf.titulo(f"Planilla · {carpeta}")
    plan, avisos = plan_campo.leer(carpeta)
    for a in avisos:
        inf.mal(a, "corregir la planilla en Google Sheets y volver a exportar el CSV")
    if plan.empty:
        inf.info("no hay planilla (CSV) para cruzar")
        return
    if fotos.empty:
        inf.info(f"{len(plan)} filas de planilla, pero no hay fotos para cruzar")
        return
    t = pd.to_datetime(fotos["fecha"] + " " + fotos["hora"], errors="coerce")
    usadas = set()
    sin_fotos = []
    for _, f in plan.iterrows():
        cerca = (t - f["t"]).abs() <= pd.Timedelta(minutes=plan_campo.VENTANA_MIN)
        if cerca.any():
            usadas |= set(fotos.loc[cerca, "sitio"])
        else:
            sin_fotos.append(str(f["n"] or f["t"]))
    if sin_fotos:
        inf.mal(f"{len(sin_fotos)} filas sin fotos a ± {plan_campo.VENTANA_MIN} min (n.º {', '.join(sin_fotos[:8])})",
                "revisar la HORA anotada (formato 24 h o con a. m./p. m.) y la fecha")
    else:
        inf.ok(f"las {len(plan)} filas de la planilla tienen fotos")
    huerfanos = sorted(set(fotos["sitio"]) - usadas)
    if huerfanos:
        inf.mal(f"{len(huerfanos)} puntos con fotos pero sin fila en la planilla", "agregar la fila (hora del punto, clase, superficie…)")
    else:
        inf.ok("todos los puntos con fotos están en la planilla")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phyphox", type=Path, default=PHYPHOX)
    ap.add_argument("--fotos", type=Path, default=CRUDAS)
    ap.add_argument("--planilla", type=Path, default=PLANILLA)
    ap.add_argument("--salida", type=Path, default=DATA / "raw" / "validacion_campo.md")
    a = ap.parse_args()
    inf = Informe()
    inf.lineas.append(f"# Validación de campo · {datetime.now(ZONA_LOCAL):%Y-%m-%d %H:%M}")
    if a.phyphox.exists():
        ent = entradas_phyphox(a.phyphox)
        if not ent:
            inf.titulo("phyphox")
            inf.info(f"no hay recorridos en {a.phyphox}")
        for p in ent:
            revisar_phyphox(p, inf)
    else:
        inf.titulo("phyphox")
        inf.info(f"no existe {a.phyphox} (bajar de Drive VIA_VIVA/02_DATOS/phyphox/)")
    fotos = revisar_fotos(a.fotos, inf) if a.fotos.exists() else pd.DataFrame()
    if not a.fotos.exists():
        inf.titulo("Fotos")
        inf.info(f"no existe {a.fotos} (bajar de Drive VIA_VIVA/02_DATOS/fotos/)")
    revisar_planilla(a.planilla, fotos, inf)
    inf.lineas += ["", f"**Total: {inf.bien} bien, {inf.corregir} por corregir.**"]
    texto = "\n".join(inf.lineas) + "\n"
    a.salida.parent.mkdir(parents=True, exist_ok=True)
    a.salida.write_text(texto, encoding="utf-8")
    print(texto)
    print(f"(guardado en {a.salida})")
    sys.exit(0)


if __name__ == "__main__":
    main()
