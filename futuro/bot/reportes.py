"""Lógica de los reportes ciudadanos (sin Telegram): guardar, consultar y cambiar estado.

Privacidad:
  * del usuario solo se guarda un hash con sal de su id de Telegram (BOT_SAL_HASH en .env), nunca el id;
  * las fotos quedan en data/fotos_bot/ (ignorada por Git) y NO se publican en el mapa.
"""
from __future__ import annotations

import hashlib
import math
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from db.acceso import ahora_utc, conectar  # noqa: E402
from etl.geohash import codificar  # noqa: E402

CARPETA_FOTOS = RAIZ / "data" / "fotos_bot"
TIPOS = {"hueco": "Hueco", "resalto": "Resalto", "obstaculo": "Obstáculo", "otro": "Otro"}
ESTADOS = ["nuevo", "confirmado", "en_reparacion", "reparado", "descartado"]
NOMBRE_ESTADO = {"nuevo": "nuevo", "confirmado": "confirmado", "en_reparacion": "en reparación",
                 "reparado": "reparado", "descartado": "descartado"}
TUNJA = (5.5353, -73.3678)
RADIO_MAX_KM = 25.0     # reportes más lejos se rechazan (fuera del municipio y alrededores)


def hash_usuario(id_telegram: int) -> str:
    sal = os.getenv("BOT_SAL_HASH")
    if not sal:
        raise RuntimeError("Falta BOT_SAL_HASH en .env (una frase larga al azar; ver .env.example)")
    return hashlib.sha256(f"{sal}:{id_telegram}".encode()).hexdigest()


def distancia_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def ubicacion_valida(lat: float, lon: float) -> bool:
    return distancia_km(lat, lon, *TUNJA) <= RADIO_MAX_KM


def guardar_reporte(hash_usr: str, tipo: str, lat: float, lon: float, foto_ruta: str | None = None,
                    descripcion: str | None = None, canal: str = "telegram", con=None,
                    sugerencia: dict | None = None) -> int:
    """Inserta el reporte con estado 'nuevo' y devuelve su número. sugerencia = salida de dataset.clasificar."""
    if tipo not in TIPOS:
        raise ValueError(f"tipo inválido: {tipo}")
    if not ubicacion_valida(lat, lon):
        raise ValueError("ubicación fuera de Tunja")
    con = con or conectar()
    ahora = ahora_utc()
    s = sugerencia or {}
    with con:
        cur = con.execute(
            "INSERT INTO reportes (canal, hash_usuario, ts_utc, lat, lon, tipo, descripcion, foto_ruta, estado, "
            "ts_estado, geohash7, ts_carga, clase_sugerida, confianza_sugerida, modelo_sugerencia) "
            "VALUES (?,?,?,?,?,?,?,?,'nuevo',?,?,?,?,?,?)",
            (canal, hash_usr, ahora, lat, lon, tipo, descripcion, foto_ruta, ahora, codificar(lat, lon, 7), ahora,
             s.get("clase"), s.get("confianza"), s.get("version") and s["version"] + ("" if not s.get("sintetico") or
                                                                                       "SINTETICO" in s["version"]
                                                                                       else "-SINTETICO")))
    return cur.lastrowid


def consultar(id_reporte: int, hash_usr: str | None = None, con=None) -> dict | None:
    """Estado de un reporte. Si se da hash_usr, solo devuelve reportes de ese usuario."""
    con = con or conectar()
    fila = con.execute("SELECT id_reporte, tipo, estado, ts_utc, ts_estado, hash_usuario FROM reportes "
                       "WHERE id_reporte = ?", (id_reporte,)).fetchone()
    if fila is None or (hash_usr is not None and fila[5] != hash_usr):
        return None
    return {"id": fila[0], "tipo": fila[1], "estado": fila[2], "creado": fila[3], "actualizado": fila[4]}


def mis_reportes(hash_usr: str, limite: int = 10, con=None) -> list[dict]:
    con = con or conectar()
    filas = con.execute("SELECT id_reporte, tipo, estado, ts_utc FROM reportes WHERE hash_usuario = ? "
                        "ORDER BY id_reporte DESC LIMIT ?", (hash_usr, limite)).fetchall()
    return [{"id": f[0], "tipo": f[1], "estado": f[2], "creado": f[3]} for f in filas]


def cambiar_estado(id_reporte: int, estado: str, con=None) -> bool:
    if estado not in ESTADOS:
        raise ValueError(f"estado inválido: {estado} (válidos: {', '.join(ESTADOS)})")
    con = con or conectar()
    with con:
        cur = con.execute("UPDATE reportes SET estado = ?, ts_estado = ? WHERE id_reporte = ?",
                          (estado, ahora_utc(), id_reporte))
    return cur.rowcount == 1
