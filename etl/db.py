"""Conexión a SQLite y creación del esquema (db/schema.sql)."""
import sqlite3
from datetime import datetime, timezone

from etl.config import DB_PATH, ESQUEMA_SQL


def ahora_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def conectar(ruta=DB_PATH) -> sqlite3.Connection:
    """Abre la base (la crea si no existe) y aplica el esquema."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA_SQL.read_text(encoding="utf-8"))
    return con


if __name__ == "__main__":
    con = conectar()
    tablas = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    print(f"Base: {DB_PATH}")
    print("Tablas:", ", ".join(tablas))
