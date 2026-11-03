"""Compatibilidad: el ETL abre la base por la capa de acceso db/acceso.py."""
from db.acceso import ahora_utc, conectar, resumen, url_base  # noqa: F401

if __name__ == "__main__":
    print(f"Base: {url_base()}")
    print("Tablas:", ", ".join(resumen(conectar())))
