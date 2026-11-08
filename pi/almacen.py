"""SQLite en la Pi (fuente de verdad, funciona sin internet): eventos del nodo, índice de calles y consultas del
tablero de la Alcaldía. Misma base y esquema que el PC (`db/schema.sql`, `db.acceso.conectar`).

Prioridad de atención = severidad × tránsito × reincidencia, igual que `dashboard-java/.../PrioridadPeligros.java`.
"""
from __future__ import annotations

import hmac
import threading
from datetime import datetime, timezone

from db.acceso import conectar as _conectar
from pi.estructuras import (GrafoCalles, IndiceGeohash, TablaHash, geohash, leer_wkt_linea, top_k)

CLASES_VIA = ("hueco", "resalto", "impacto_fuerte", "normal", "obstaculo")
ESTADOS = ("nuevo", "confirmado", "en_reparacion", "reparado", "descartado")
MODELO_NODO = "umbral-v1"           # el nodo aún no clasifica con el modelo (entrenado con datos SINTÉTICOS)


def ahora_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def conectar(url: str | None = None):
    """Conexión con espera (varios hilos escriben) y WAL (lectores no bloquean al escritor)."""
    con = _conectar(url)
    con.execute("PRAGMA busy_timeout = 5000")
    try:
        con.execute("PRAGMA journal_mode = WAL")
    except Exception:
        pass
    return con


# ------------------------------------------------------------------------------------------------ eventos del nodo
def guardar_eventos(lote: list[dict], id_nodo: str, origen: str, url: str | None = None) -> int:
    """UPSERT por (id_nodo, ts_utc): si luego llega una etiqueta, se actualiza el mismo evento."""
    con = conectar(url)
    try:
        filas = [(id_nodo, e["ts_utc"], e["lat"], e["lon"], e.get("vel_kmh"), e["clase"], e.get("etiqueta_manual"),
                  origen, e.get("razon"), MODELO_NODO, e.get("id_tramo"), geohash(e["lat"], e["lon"], 7), ahora_utc())
                 for e in lote if e.get("lat") is not None]
        con.executemany(
            "INSERT INTO eventos (id_nodo, ts_utc, lat, lon, velocidad_kmh, clase, etiqueta_manual, origen, "
            "razon_umbral, modelo_version, id_tramo, geohash7, ts_carga) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT (id_nodo, ts_utc) DO UPDATE SET clase = excluded.clase, "
            "etiqueta_manual = excluded.etiqueta_manual, id_tramo = excluded.id_tramo", filas)
        con.commit()
        return len(filas)
    finally:
        con.close()


# ------------------------------------------------------------------------------------------------ calles en memoria
class Calles:
    """Tramos, grafo e índice geohash cargados una vez (5 775 tramos ≈ 1–3 s en la Pi, en un hilo aparte)."""

    def __init__(self):
        self.listo = threading.Event()
        self.indice = IndiceGeohash()
        self.grafo = GrafoCalles()
        self.info: TablaHash[int, dict] = TablaHash(8192)
        self.error: str | None = None

    def cargar(self, url: str | None = None) -> "Calles":
        try:
            con = conectar(url)
            for t, u, v, nombre, tipo, barrio, largo, wkt in con.execute(
                    "SELECT id_tramo, osm_u, osm_v, nombre, tipo_via, barrio, longitud_m, geometria_wkt FROM tramos"):
                puntos = leer_wkt_linea(wkt)
                self.indice.agregar(t, puntos)
                self.grafo.agregar_tramo(t, u, v)
                self.info.poner(t, {"id_tramo": t, "nombre": nombre, "tipo_via": tipo, "barrio": barrio,
                                    "longitud_m": round(largo or 0, 1),
                                    "puntos": [[round(a, 6), round(b, 6)] for a, b in puntos]})
            con.close()
        except Exception as err:
            self.error = str(err)
        self.listo.set()
        return self

    def ajustar(self, lat: float, lon: float, max_m: float = 25.0):
        if not self.listo.is_set() or len(self.indice) == 0:
            return None, float("inf")
        return self.indice.mas_cercano(lat, lon, max_m)


# ------------------------------------------------------------------------------------------------ tablero
def corridas_riesgo(con) -> list[dict]:
    filas = con.execute("SELECT modelo, version_modelo, fecha_calculo, COUNT(*), MAX(fuente_etiquetas) FROM riesgo "
                        "GROUP BY modelo, version_modelo, fecha_calculo ORDER BY fecha_calculo DESC, modelo").fetchall()
    return [{"modelo": m, "version": v, "fecha": f, "tramos": n, "fuente": fu,
             "demo": "DEMO" in (v or "").upper() or "SINTETICO" in (v or "").upper()} for m, v, f, n, fu in filas]


def riesgo(con, calles: Calles, modelo: str | None = None, version: str | None = None) -> dict:
    """Probabilidad por tramo de una corrida (la más reciente si no se pide otra) + top-10 con el montículo."""
    corridas = corridas_riesgo(con)
    elegida = next((c for c in corridas if (modelo is None or c["modelo"] == modelo)
                    and (version is None or c["version"] == version)), None)
    if elegida is None:
        return {"corrida": None, "corridas": corridas, "tramos": [], "top10": [], "zonas": []}
    filas = con.execute("SELECT id_tramo, probabilidad, rango, reportado FROM riesgo WHERE modelo = ? AND "
                        "version_modelo = ? AND fecha_calculo = ?",
                        (elegida["modelo"], elegida["version"], elegida["fecha"])).fetchall()
    tramos = []
    for t, p, r, rep in filas:
        info = calles.info.obtener(t) or {"id_tramo": t}
        tramos.append({**info, "probabilidad": round(p, 4), "rango": r, "reportado": bool(rep)})
    top = top_k(tramos, 10, lambda x: (x["probabilidad"], -x["id_tramo"]))
    no_reportados = top_k([x for x in tramos if not x["reportado"]], 10, lambda x: (x["probabilidad"], -x["id_tramo"]))
    umbral = top[-1]["probabilidad"] if top else 1.0
    zonas = calles.grafo.zonas({x["id_tramo"] for x in tramos if x["probabilidad"] >= max(umbral, 0.5)})
    return {"corrida": elegida, "corridas": corridas, "tramos": tramos,
            "top10": [{k: v for k, v in x.items() if k != "puntos"} for x in top],
            "top10_no_reportados": [x["id_tramo"] for x in no_reportados],
            "zonas": zonas[:10]}


def nivel_severidad(sev01, clase) -> int:
    if sev01 is not None:
        s = max(0.0, min(1.0, float(sev01)))
        return 1 if s < 1 / 3 else 2 if s < 2 / 3 else 3
    return {"hueco": 3, "impacto_fuerte": 3, "resalto": 1, "vehiculo_varado": 1}.get(clase or "", 2)


def peso_transito(tipo_via) -> int:
    mejor = 1
    for parte in (tipo_via or "").split(";"):
        t = parte.strip().lower().removesuffix("_link")
        mejor = max(mejor, 3 if t in ("motorway", "trunk", "primary") else 2 if t in ("secondary", "tertiary") else 1)
    return mejor


def peligros(con, calles: Calles, k: int = 20) -> dict:
    """Reportes y eventos abiertos ordenados por prioridad = severidad × tránsito × reincidencia.
    Dos pasadas O(n) (conteo por tramo en la TablaHash) + top-k con el montículo O(n + k log n)."""
    lista = []
    for i, ts, lat, lon, tipo, desc, estado, t, hu in con.execute(
            "SELECT id_reporte, ts_utc, lat, lon, tipo, descripcion, estado, id_tramo, hash_usuario FROM reportes"):
        demo = "DEMO" in f"{desc or ''}{hu or ''}".upper()
        lista.append({"tipo_fila": "reporte", "id": i, "ts_utc": ts, "lat": lat, "lon": lon, "clase": tipo,
                      "severidad": None, "estado": estado, "id_tramo": t, "demo": demo, "descripcion": desc,
                      "cerrado": estado in ("reparado", "descartado")})
    for i, ts, lat, lon, clase, sev, origen, nodo, t in con.execute(
            "SELECT id_evento, ts_utc, lat, lon, clase, severidad, origen, id_nodo, id_tramo FROM eventos "
            f"WHERE clase IN ({','.join('?' * len(CLASES_VIA))}) AND clase != 'normal'", CLASES_VIA):
        lista.append({"tipo_fila": "evento", "id": i, "ts_utc": ts, "lat": lat, "lon": lon, "clase": clase,
                      "severidad": sev, "estado": None, "id_tramo": t, "origen": origen,
                      "demo": origen == "simulado" or "DEMO" in (nodo or "").upper(), "cerrado": False})
    conteo: TablaHash[tuple, int] = TablaHash(max(16, 2 * len(lista)))
    for p in lista:
        if p["id_tramo"] is not None and not p["cerrado"]:
            conteo.sumar((p["id_tramo"], p["demo"]))
    for p in lista:
        info = calles.info.obtener(p["id_tramo"]) if p["id_tramo"] is not None else None
        p["nombre_via"] = (info or {}).get("nombre")
        p["nivel_severidad"] = nivel_severidad(p["severidad"], p["clase"])
        p["peso_transito"] = peso_transito((info or {}).get("tipo_via"))
        p["reincidencia"] = conteo.obtener((p["id_tramo"], p["demo"]), 1) if p["id_tramo"] is not None else 1
        p["prioridad"] = 0 if p["cerrado"] else p["nivel_severidad"] * p["peso_transito"] * p["reincidencia"]
    # Lo real va antes que lo DEMO/simulado (reproducciones de la demo) aunque tenga menos prioridad.
    orden = top_k(lista, k, lambda p: (not p["demo"], p["prioridad"], p["nivel_severidad"], p["ts_utc"] or "",
                                       p["tipo_fila"] == "reporte", -p["id"]))
    return {"total": len(lista), "abiertos": sum(not p["cerrado"] for p in lista), "top": orden,
            "con_demo": any(p["demo"] for p in lista)}


def reportes(con, limite: int = 200) -> list[dict]:
    cols = ["id_reporte", "canal", "ts_utc", "lat", "lon", "tipo", "descripcion", "estado", "ts_estado", "id_tramo",
            "clase_sugerida", "confianza_sugerida", "modelo_sugerencia"]
    return [dict(zip(cols, f)) for f in con.execute(
        f"SELECT {', '.join(cols)} FROM reportes ORDER BY ts_utc DESC LIMIT ?", (limite,))]


def cambiar_estado(con, id_reporte: int, estado: str) -> bool:
    if estado not in ESTADOS:
        raise ValueError(f"estado inválido: {estado}")
    n = con.execute("UPDATE reportes SET estado = ?, ts_estado = ? WHERE id_reporte = ?",
                    (estado, ahora_utc(), id_reporte)).rowcount
    con.commit()
    return n == 1


def clave_valida(enviada: str | None, esperada: str | None) -> bool:
    return bool(esperada) and enviada is not None and hmac.compare_digest(enviada.encode(), esperada.encode())
