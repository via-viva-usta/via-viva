"""Definiciones compartidas del dataset de fotos de VÍA VIVA (esquema, clases, rutas y utilidades).

El esquema de metadatos es UNO solo para ingesta, etiquetador, escala y modelo. Si se cambia aquí, cambia en todos.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent           # carpeta via-viva/
DATA = RAIZ / "data"

# Carpetas por defecto (data/ está ignorada por Git: las fotos y sus metadatos NO se suben)
CRUDAS = DATA / "raw" / "fotos"                          # data/raw/fotos/AAAA-MM-DD_nombre/*.jpg|heic
PROCESADO = DATA / "procesado"                           # fotos/ difuminadas + metadatos.csv + calidad.csv
NODO = DATA / "raw" / "nodo"                             # copias de la microSD (ambiente_NNN.csv)
# Lo sintético va SIEMPRE aparte para que nunca se mezcle con lo real
CRUDAS_SINTETICO = DATA / "raw" / "fotos_sintetico"
PROCESADO_SINTETICO = DATA / "procesado_sintetico"

ZONA_LOCAL = timezone(timedelta(hours=-5))               # Colombia: UTC-5 todo el año (sin horario de verano)
TUNJA = (5.5353, -73.3678)                               # centro aproximado (lat, lon)

# ---- Clases (9) y meta ----
CLASES = ["hueco", "resalto", "grieta", "parche", "tapa", "obstaculo", "linea_carril", "paso_peatonal", "via_buena"]
CLASES_DANO = {"hueco", "grieta", "parche", "tapa", "obstaculo"}   # llevan severidad
META_POR_CLASE = 50
META_TOTAL = 500

SEVERIDADES = ["leve", "media", "alta"]
ANGULOS = ["contexto", "frente", "lado", "cenital"]
LUCES = ["sol", "sombra", "nublado", "noche"]
TIPOS_VIA = ["arterial", "colectora", "local", "destapada", "otra"]
FUENTES_CLIMA = ["nodo", "termohigrometro", "api"]
MOMENTOS = ["madrugada", "manana", "mediodia", "tarde", "noche"]

# Esquema del CSV de metadatos (orden de columnas). Las dos últimas son opcionales: medidas con regla en campo,
# para validar el área que calcula dataset/escala.py.
COLUMNAS = ["id", "archivo", "autor", "fecha", "hora", "momento_dia", "lat", "lon", "id_tramo", "barrio", "tipo_via",
            "clase", "severidad", "angulo", "distancia_m", "luz", "superficie_mojada", "temperatura", "humedad", "lux",
            "fuente_clima", "lluvia_ideam", "notas", "largo_regla_cm", "ancho_regla_cm"]
# Lo que llena una persona (la ingesta no lo pisa si ya tiene valor)
COLUMNAS_HUMANAS = ["clase", "severidad", "angulo", "distancia_m", "luz", "superficie_mojada", "tipo_via", "notas",
                    "largo_regla_cm", "ancho_regla_cm"]

# Columnas técnicas (calidad.csv): no son del esquema, sirven para el reporte y para trazar el origen
COLUMNAS_CALIDAD = ["id", "origen", "sha1", "dhash", "ancho_px", "alto_px", "nitidez", "borrosa", "sin_gps", "sin_fecha",
                    "duplicado_de", "caras", "placas", "utc"]

UMBRAL_NITIDEZ = 60.0       # varianza del laplaciano (imagen a 1024 px); menor = borrosa. Ajustar con fotos reales
DHASH_CASI_IGUAL = 4        # bits distintos para considerar dos fotos casi iguales


def momento_dia(hora_local: int) -> str:
    """Tunja está cerca del ecuador: amanece ~5:45 y oscurece ~18:00 todo el año."""
    if hora_local < 6:
        return "madrugada"
    if hora_local < 11:
        return "manana"
    if hora_local < 14:
        return "mediodia"
    if hora_local < 18:
        return "tarde"
    return "noche"


def autor_de_carpeta(nombre: str) -> str:
    """'2026-11-04_pipe' → 'pipe'. Si la carpeta no sigue el formato, se usa el nombre completo."""
    partes = nombre.split("_", 1)
    if len(partes) == 2 and len(partes[0]) == 10 and partes[0][4] == "-":
        return partes[1].strip().lower()
    return nombre.strip().lower()


def distancia_m(lat1, lon1, lat2, lon2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def leer_metadatos(ruta: Path) -> pd.DataFrame:
    if not ruta.exists():
        return pd.DataFrame(columns=COLUMNAS)
    df = pd.read_csv(ruta, dtype=str, keep_default_na=False)
    for c in COLUMNAS:
        if c not in df.columns:
            df[c] = ""
    return df[COLUMNAS]


def guardar_csv(df: pd.DataFrame, ruta: Path) -> None:
    """Escritura atómica: si se corta a la mitad, el CSV anterior queda intacto."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    df.to_csv(tmp, index=False, encoding="utf-8")
    os.replace(tmp, ruta)


def sitios(df: pd.DataFrame, radio_m: float = 15.0, ventana_min: float = 10.0) -> pd.Series:
    """Agrupa las fotos tomadas en el MISMO punto (para dividir train/val/test por sitio, nunca por foto).

    Dos fotos son del mismo sitio si están a ≤ radio_m (con GPS) o, sin GPS, si son del mismo autor y se tomaron
    con ≤ ventana_min minutos de diferencia. Se unen por componentes conexas (unión-búsqueda).
    """
    n = len(df)
    padre = list(range(n))

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    lat = pd.to_numeric(df["lat"], errors="coerce").to_numpy()
    lon = pd.to_numeric(df["lon"], errors="coerce").to_numpy()
    t = pd.to_datetime(df["fecha"] + " " + df["hora"], errors="coerce")
    autor = df["autor"].to_numpy()
    for i in range(n):
        for j in range(i + 1, n):
            mismo = False
            if not (math.isnan(lat[i]) or math.isnan(lat[j])):
                mismo = distancia_m(lat[i], lon[i], lat[j], lon[j]) <= radio_m
            elif autor[i] == autor[j] and pd.notna(t.iloc[i]) and pd.notna(t.iloc[j]):
                mismo = abs((t.iloc[i] - t.iloc[j]).total_seconds()) <= ventana_min * 60
            if mismo:
                padre[raiz(i)] = raiz(j)
    raices = [raiz(i) for i in range(n)]
    orden = {r: k for k, r in enumerate(dict.fromkeys(raices))}
    return pd.Series([f"S{orden[r]:04d}" for r in raices], index=df.index, name="sitio")


def utc_a_local(t: datetime) -> datetime:
    return t.astimezone(ZONA_LOCAL)
