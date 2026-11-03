"""Rutas y configuración comunes del ETL (lee .env si existe)."""
import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent  # carpeta via-viva/
load_dotenv(RAIZ / ".env")

DATA = RAIZ / "data"
OSM_DIR = DATA / "osm"
ESQUEMA_SQL = RAIZ / "db" / "schema.sql"

# La base se abre por la capa de acceso db/acceso.py (VIA_VIVA_DB_URL en .env)

USER_AGENT = os.getenv(
    "SCRAPER_USER_AGENT",
    "ViaVivaBot/0.1 (proyecto academico USTA Tunja)",
)
SOCRATA_APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN") or None

# Centro aproximado de Tunja (Plaza de Bolívar), para distancias y filtros
TUNJA_LAT, TUNJA_LON = 5.5353, -73.3678
