"""Capa de acceso a datos de VÍA VIVA.

Todo el código (ETL, modelo de riesgo, bot, mapa web) abre la base SOLO por aquí. Así, migrar de SQLite a
PostgreSQL/PostGIS más adelante es cambiar este archivo y la variable de entorno, no todo el proyecto.

Configuración (en .env, ver .env.example):
  VIA_VIVA_DB_URL = sqlite:///data/via_viva.db          (por defecto; ruta relativa a la carpeta via-viva/)
  VIA_VIVA_DB     = data/via_viva.db                    (forma antigua, se sigue aceptando)
  # futuro: VIA_VIVA_DB_URL = postgresql://usuario:clave@servidor:5432/via_viva

Uso:
  from db.acceso import conectar, leer_df
  con = conectar()                       # crea la base si no existe y aplica db/schema.sql
  df = leer_df("SELECT * FROM tramos LIMIT 5")
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent      # carpeta via-viva/
# Columnas agregadas después de crear la primera base: se añaden solas a las bases existentes.
COLUMNAS_NUEVAS = [("riesgo", "fuente_etiquetas", "TEXT"),
                   # 5-nov: sugerencia de la CNN de fotos en los reportes del bot (no reemplaza la revisión humana)
                   ("reportes", "clase_sugerida", "TEXT"), ("reportes", "confianza_sugerida", "REAL"),
                   ("reportes", "modelo_sugerencia", "TEXT")]
ESQUEMA_SQL = Path(__file__).resolve().parent / "schema.sql"

try:                                               # python-dotenv es opcional para esta capa
    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env")
except ImportError:
    pass


def ahora_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def url_base() -> str:
    url = os.getenv("VIA_VIVA_DB_URL")
    if url:
        return url
    return "sqlite:///" + os.getenv("VIA_VIVA_DB", "data/via_viva.db")


def motor(url: str | None = None) -> str:
    """'sqlite' o 'postgresql'."""
    return (url or url_base()).split(":", 1)[0].split("+", 1)[0]


def ruta_sqlite(url: str | None = None) -> Path:
    url = url or url_base()
    if motor(url) != "sqlite":
        raise ValueError(f"{url} no es una base SQLite")
    ruta = Path(url.split(":///", 1)[1])
    return ruta if ruta.is_absolute() else RAIZ / ruta


def conectar(url: str | None = None, solo_lectura: bool = False, aplicar_esquema: bool = True):
    """Abre la base. En SQLite la crea si no existe, activa llaves foráneas y aplica el esquema."""
    url = url or url_base()
    if motor(url) == "sqlite":
        ruta = ruta_sqlite(url)
        if solo_lectura:
            con = sqlite3.connect(f"file:{ruta.as_posix()}?mode=ro", uri=True)
        else:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            con = sqlite3.connect(ruta)
            con.execute("PRAGMA foreign_keys = ON")
            if aplicar_esquema:
                con.executescript(ESQUEMA_SQL.read_text(encoding="utf-8"))
                migrar(con)
        return con
    if motor(url) == "postgresql":
        raise NotImplementedError(
            "PostgreSQL/PostGIS todavía no está implementado. Pasos para migrar: (1) traducir db/schema.sql "
            "(AUTOINCREMENT → GENERATED ALWAYS AS IDENTITY, geometria_wkt → geometry(LineString, 4326)); "
            "(2) aquí, conectar con psycopg y devolver la conexión; (3) cambiar los '?' de las consultas por '%s' "
            "(usar marcador() de este módulo).")
    raise ValueError(f"Motor de base de datos no soportado: {url}")


def migrar(con) -> None:
    """ALTER TABLE ... ADD COLUMN para las columnas que una base vieja todavía no tiene."""
    for tabla, columna, tipo in COLUMNAS_NUEVAS:
        existentes = {r[1] for r in con.execute(f"PRAGMA table_info({tabla})")}
        if columna not in existentes:
            con.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
    con.commit()


def marcador(url: str | None = None) -> str:
    """Marcador de parámetros del motor: '?' en SQLite, '%s' en PostgreSQL."""
    return "?" if motor(url) == "sqlite" else "%s"


def leer_df(sql: str, params=None, con=None):
    """Consulta → pandas.DataFrame (pandas se importa solo si se usa)."""
    import pandas as pd
    propia = con is None
    con = con or conectar()
    try:
        return pd.read_sql(sql, con, params=params)
    finally:
        if propia:
            con.close()


def resumen(con=None) -> dict:
    """Filas por tabla, para verificar una reconstrucción."""
    propia = con is None
    con = con or conectar()
    try:
        tablas = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tablas}
    finally:
        if propia:
            con.close()


if __name__ == "__main__":
    print("Base:", url_base(), "→", ruta_sqlite() if motor() == "sqlite" else "")
    for tabla, n in resumen().items():
        print(f"  {tabla:<18} {n}")
