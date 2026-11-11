"""SQLite en la Pi (fuente de verdad, funciona sin internet): eventos del nodo, huecos con su estado, índice de
calles y consultas del tablero. Misma base y esquema que el PC (`db/schema.sql`, `db.acceso.conectar`).

- Un **hueco** agrupa las detecciones (eventos `hueco` o `impacto_fuerte` sin clasificar) a ≤ 10 m entre sí.
  Estado: detectado → verificado → reparado (o descartado). Si un hueco reparado se vuelve a detectar, se reabre.
- Prioridad de atención = severidad × tránsito × reincidencia, igual que `dashboard-java/.../PrioridadPeligros.java`.
"""
from __future__ import annotations

import threading
from datetime import UTC, datetime

from db.acceso import conectar as _conectar
from viaviva.estructuras import (
    GrafoCalles,
    IndiceGeohash,
    TablaHash,
    distancia_m,
    geohash,
    leer_wkt_linea,
    top_k,
    vecinos_geohash,
)

CLASES_VIA = ("hueco", "resalto", "impacto_fuerte", "normal", "obstaculo")
CLASES_HUECO = ("hueco", "impacto_fuerte")
ESTADOS_HUECO = ("detectado", "verificado", "reparado", "descartado")
ESTADOS_REPORTE = ("nuevo", "confirmado", "en_reparacion", "reparado", "descartado")
RADIO_HUECO_M = 10.0                # dos pasadas por el mismo hueco caen a < 10 m con GPS de ~3–5 m
MODELO_NODO = "umbral-v1"           # el nodo aún no clasifica con el modelo (entrenado con datos SINTÉTICOS)
_candado_huecos = threading.Lock()


def ahora_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def conectar(url: str | None = None):
    """Conexión con espera (varios hilos escriben) y WAL (lectores no bloquean al escritor)."""
    con = _conectar(url)
    con.execute("PRAGMA busy_timeout = 5000")
    try:
        con.execute("PRAGMA journal_mode = WAL")
    except Exception:
        pass
    return con


def filas(con, sql: str, params=()) -> list[dict]:
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, f)) for f in cur.fetchall()]


def es_demo(*textos) -> bool:
    t = " ".join(str(x or "") for x in textos).upper()
    return "DEMO" in t or "SINTETICO" in t or "SINTÉTICO" in t


# ------------------------------------------------------------------------------------------------ eventos del nodo
def guardar_eventos(lote: list[dict], id_nodo: str, origen: str, url: str | None = None) -> int:
    """UPSERT por (id_nodo, ts_utc): si luego llega una etiqueta, se actualiza el mismo evento."""
    con = conectar(url)
    try:
        datos = [(id_nodo, e["ts_utc"], e["lat"], e["lon"], e.get("vel_kmh"), e["clase"], e.get("etiqueta_manual"),
                  origen, e.get("razon"), MODELO_NODO, e.get("id_tramo"), geohash(e["lat"], e["lon"], 7), ahora_utc(),
                  SEVERIDAD_NUM.get(e.get("severidad")), e.get("confianza"))
                 for e in lote if e.get("lat") is not None]
        con.executemany(
            "INSERT INTO eventos (id_nodo, ts_utc, lat, lon, velocidad_kmh, clase, etiqueta_manual, origen, "
            "razon_umbral, modelo_version, id_tramo, geohash7, ts_carga, severidad, confianza) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT (id_nodo, ts_utc) DO UPDATE SET clase = excluded.clase, "
            "etiqueta_manual = excluded.etiqueta_manual, id_tramo = excluded.id_tramo", datos)
        con.commit()
        agrupar_huecos(con)
        return len(datos)
    finally:
        con.close()


# ------------------------------------------------------------------------------------------------ huecos
def _registrar_cambio(con, tabla, id_fila, antes, despues, usuario, origen, nota=None) -> None:
    con.execute("INSERT INTO cambios_estado (tabla, id_fila, estado_antes, estado_despues, usuario, origen, nota, "
                "ts_utc) VALUES (?,?,?,?,?,?,?,?)", (tabla, id_fila, antes, despues, usuario, origen, nota, ahora_utc()))


def _recontar(con, ids: set[int]) -> None:
    for h in ids:
        n, lat, lon, pri, ult, hay_hueco, sev = con.execute(
            "SELECT COUNT(*), AVG(lat), AVG(lon), MIN(ts_utc), MAX(ts_utc), MAX(clase = 'hueco'), MAX(severidad) "
            "FROM eventos WHERE id_hueco = ?", (h,)).fetchone()
        if n == 0:                         # todas sus detecciones se reetiquetaron como otra cosa
            antes = con.execute("SELECT estado FROM huecos WHERE id_hueco = ?", (h,)).fetchone()[0]
            con.execute("UPDATE huecos SET n_detecciones = 0, estado = 'descartado', ts_estado = ?, "
                        "usuario_estado = 'sistema', nota = 'sin detecciones (reetiquetadas)' WHERE id_hueco = ?",
                        (ahora_utc(), h))
            if antes != "descartado":
                _registrar_cambio(con, "huecos", h, antes, "descartado", "sistema", "web", "sin detecciones")
            continue
        con.execute("UPDATE huecos SET n_detecciones = ?, lat = ?, lon = ?, geohash7 = ?, primera_ts = ?, "
                    "ultima_ts = ?, clase = ?, severidad = ? WHERE id_hueco = ?",
                    (n, lat, lon, geohash(lat, lon, 7), pri, ult, "hueco" if hay_hueco else "impacto_fuerte",
                     severidad_texto(sev), h))


def agrupar_huecos(con) -> int:
    """Asigna cada detección nueva a un hueco a ≤ RADIO_HUECO_M (celda geohash-7 y sus 8 vecinas: O(1) por
    evento) o crea uno nuevo. Lo simulado/DEMO se agrupa aparte. Devuelve cuántos eventos asignó."""
    with _candado_huecos:
        tocados: set[int] = set()
        sueltos = con.execute("SELECT id_evento, id_hueco FROM eventos WHERE id_hueco IS NOT NULL AND clase NOT IN "
                              f"({','.join('?' * len(CLASES_HUECO))})", CLASES_HUECO).fetchall()
        for id_ev, h in sueltos:
            con.execute("UPDATE eventos SET id_hueco = NULL WHERE id_evento = ?", (id_ev,))
            tocados.add(h)
        pendientes = filas(con, "SELECT id_evento, ts_utc, lat, lon, clase, origen, id_nodo, id_tramo, modelo_version "
                                f"FROM eventos WHERE id_hueco IS NULL AND clase IN ({','.join('?' * len(CLASES_HUECO))}) "
                                "ORDER BY ts_utc", CLASES_HUECO)
        for e in pendientes:
            simulado = int(e["origen"] == "simulado" or es_demo(e["id_nodo"], e["modelo_version"]))
            celdas = vecinos_geohash(geohash(e["lat"], e["lon"], 7))
            cand = con.execute(f"SELECT id_hueco, lat, lon, estado, ts_estado FROM huecos WHERE simulado = ? AND "
                               f"geohash7 IN ({','.join('?' * len(celdas))})", (simulado, *celdas)).fetchall()
            mejor = min(cand, key=lambda c: distancia_m(e["lat"], e["lon"], c[1], c[2]), default=None)
            if mejor is not None and distancia_m(e["lat"], e["lon"], mejor[1], mejor[2]) <= RADIO_HUECO_M:
                h = mejor[0]
                if mejor[3] == "reparado" and e["ts_utc"] > (mejor[4] or ""):
                    con.execute("UPDATE huecos SET estado = 'detectado', ts_estado = ?, usuario_estado = 'sistema', "
                                "nota = 'se volvió a detectar después de reparado' WHERE id_hueco = ?", (ahora_utc(), h))
                    _registrar_cambio(con, "huecos", h, "reparado", "detectado", "sistema", "web",
                                      "se volvió a detectar después de reparado")
            else:
                h = con.execute("INSERT INTO huecos (lat, lon, geohash7, id_tramo, clase, primera_ts, ultima_ts, "
                                "simulado, ts_carga) VALUES (?,?,?,?,?,?,?,?,?)",
                                (e["lat"], e["lon"], geohash(e["lat"], e["lon"], 7), e["id_tramo"], e["clase"],
                                 e["ts_utc"], e["ts_utc"], simulado, ahora_utc())).lastrowid
            con.execute("UPDATE eventos SET id_hueco = ? WHERE id_evento = ?", (h, e["id_evento"]))
            tocados.add(h)
        _recontar(con, tocados)
        con.commit()
        return len(pendientes)


def huecos(con, calles: Calles | None = None, incluir_simulados: bool = True) -> list[dict]:
    lista = filas(con, "SELECT * FROM huecos" + ("" if incluir_simulados else " WHERE simulado = 0") +
                  " ORDER BY ultima_ts DESC")
    for h in lista:
        info = (calles.info.obtener(h["id_tramo"]) if calles and h["id_tramo"] is not None else None) or {}
        h["nombre_via"], h["barrio"], h["tipo_via"] = info.get("nombre"), info.get("barrio"), info.get("tipo_via")
        h["simulado"] = bool(h["simulado"])
    return lista


SEVERIDAD_NUM = {"baja": 0.2, "media": 0.5, "alta": 0.9}     # eventos.severidad es REAL 0–1


def severidad_texto(v) -> str | None:
    if v is None:
        return None
    return "alta" if v >= 2 / 3 else "media" if v >= 1 / 3 else "baja"


def cambiar_estado_hueco(con, id_hueco: int, estado: str, usuario: str, origen: str = "web",
                         nota: str | None = None, ts: str | None = None, confirmar: bool = True) -> bool:
    if estado not in ESTADOS_HUECO:
        raise ValueError(f"estado inválido: {estado} (use {', '.join(ESTADOS_HUECO)})")
    f = con.execute("SELECT estado FROM huecos WHERE id_hueco = ?", (id_hueco,)).fetchone()
    if f is None:
        return False
    con.execute("UPDATE huecos SET estado = ?, ts_estado = ?, usuario_estado = ?, nota = COALESCE(?, nota) "
                "WHERE id_hueco = ?", (estado, ts or ahora_utc(), usuario, nota, id_hueco))
    _registrar_cambio(con, "huecos", id_hueco, f[0], estado, usuario, origen, nota)
    if confirmar:
        con.commit()
    return True


def historial(con, tabla: str, id_fila: int) -> list[dict]:
    return filas(con, "SELECT estado_antes, estado_despues, usuario, origen, nota, ts_utc FROM cambios_estado "
                      "WHERE tabla = ? AND id_fila = ? ORDER BY id DESC", (tabla, id_fila))


# ------------------------------------------------------------------------------------------------ calles en memoria
class Calles:
    """Tramos, grafo e índice geohash cargados una vez (5 775 tramos ≈ 1–3 s en la Pi, en un hilo aparte)."""

    def __init__(self):
        self.listo = threading.Event()
        self.indice = IndiceGeohash()
        self.grafo = GrafoCalles()
        self.info: TablaHash[int, dict] = TablaHash(8192)
        self.error: str | None = None

    def cargar(self, url: str | None = None) -> Calles:
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


# ------------------------------------------------------------------------------------------------ riesgo
def corridas_riesgo(con) -> list[dict]:
    datos = con.execute("SELECT modelo, version_modelo, fecha_calculo, COUNT(*), MAX(fuente_etiquetas) FROM riesgo "
                        "GROUP BY modelo, version_modelo, fecha_calculo ORDER BY fecha_calculo DESC, modelo").fetchall()
    return [{"modelo": m, "version": v, "fecha": f, "tramos": n, "fuente": fu, "demo": es_demo(v, fu)}
            for m, v, f, n, fu in datos]


def riesgo(con, calles: Calles, modelo: str | None = None, version: str | None = None) -> dict:
    """Probabilidad por tramo de una corrida (la más reciente si no se pide otra) + top-10 con el montículo."""
    corridas = corridas_riesgo(con)
    elegida = next((c for c in corridas if (modelo is None or c["modelo"] == modelo)
                    and (version is None or c["version"] == version)), None)
    if elegida is None:
        return {"corrida": None, "corridas": corridas, "tramos": [], "top10": [], "zonas": [],
                "top10_no_reportados": []}
    datos = con.execute("SELECT id_tramo, probabilidad, rango, reportado FROM riesgo WHERE modelo = ? AND "
                        "version_modelo = ? AND fecha_calculo = ?",
                        (elegida["modelo"], elegida["version"], elegida["fecha"])).fetchall()
    tramos = []
    for t, p, r, rep in datos:
        info = calles.info.obtener(t) or {"id_tramo": t}
        tramos.append({**info, "probabilidad": round(p, 4), "rango": r, "reportado": bool(rep)})
    clave = lambda x: (x["probabilidad"], -x["id_tramo"])
    top = top_k(tramos, 10, clave)
    no_reportados = top_k([x for x in tramos if not x["reportado"]], 10, clave)
    umbral = top[-1]["probabilidad"] if top else 1.0
    zonas = calles.grafo.zonas({x["id_tramo"] for x in tramos if x["probabilidad"] >= max(umbral, 0.5)})
    return {"corrida": elegida, "corridas": corridas, "tramos": tramos,
            "top10": [{k: v for k, v in x.items() if k != "puntos"} for x in top],
            "top10_no_reportados": [x["id_tramo"] for x in no_reportados], "zonas": zonas[:10]}


# ------------------------------------------------------------------------------------------------ orden de atención
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
    """Huecos y reportes abiertos por prioridad = severidad × tránsito × reincidencia.
    Dos pasadas O(n) (conteo por tramo en la TablaHash) + top-k con el montículo O(n + k log n).
    Lo real va antes que lo DEMO/simulado aunque tenga menos prioridad."""
    lista = []
    for h in huecos(con, calles):
        # huecos.severidad es texto (baja/media/alta, la mayor de sus detecciones); nivel_severidad espera 0–1.
        # Sin severidad medida (bases viejas) queda None y se usa la clase, como antes.
        lista.append({"tipo_fila": "hueco", "id": h["id_hueco"], "ts_utc": h["ultima_ts"], "lat": h["lat"],
                      "lon": h["lon"], "clase": h["clase"], "severidad": SEVERIDAD_NUM.get(h.get("severidad")),
                      "estado": h["estado"],
                      "id_tramo": h["id_tramo"], "demo": h["simulado"], "n_detecciones": h["n_detecciones"],
                      "cerrado": h["estado"] in ("reparado", "descartado")})
    for i, ts, lat, lon, tipo, desc, estado, t, hu in con.execute(
            "SELECT id_reporte, ts_utc, lat, lon, tipo, descripcion, estado, id_tramo, hash_usuario FROM reportes"):
        lista.append({"tipo_fila": "reporte", "id": i, "ts_utc": ts, "lat": lat, "lon": lon, "clase": tipo,
                      "severidad": None, "estado": estado, "id_tramo": t, "demo": es_demo(desc, hu),
                      "cerrado": estado in ("reparado", "descartado")})
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
    orden = top_k(lista, k, lambda p: (not p["demo"], p["prioridad"], p["nivel_severidad"], p["ts_utc"] or "",
                                       p["tipo_fila"] == "reporte", -p["id"]))
    return {"total": len(lista), "abiertos": sum(not p["cerrado"] for p in lista), "top": orden,
            "con_demo": any(p["demo"] for p in lista)}


# ------------------------------------------------------------------------------------------------ reportes
def reportes(con, limite: int = 200) -> list[dict]:
    cols = ["id_reporte", "canal", "ts_utc", "lat", "lon", "tipo", "descripcion", "estado", "ts_estado", "id_tramo",
            "clase_sugerida", "confianza_sugerida", "modelo_sugerencia"]
    return filas(con, f"SELECT {', '.join(cols)} FROM reportes ORDER BY ts_utc DESC LIMIT ?", (limite,))


def cambiar_estado_reporte(con, id_reporte: int, estado: str, usuario: str) -> bool:
    if estado not in ESTADOS_REPORTE:
        raise ValueError(f"estado inválido: {estado}")
    f = con.execute("SELECT estado FROM reportes WHERE id_reporte = ?", (id_reporte,)).fetchone()
    if f is None:
        return False
    con.execute("UPDATE reportes SET estado = ?, ts_estado = ? WHERE id_reporte = ?", (estado, ahora_utc(), id_reporte))
    _registrar_cambio(con, "reportes", id_reporte, f[0], estado, usuario, "web")
    con.commit()
    return True


def resumen_estados(con, incluir_simulados: bool = True) -> dict:
    w = "" if incluir_simulados else " WHERE simulado = 0"
    d = dict(con.execute(f"SELECT estado, COUNT(*) FROM huecos{w} GROUP BY estado").fetchall())
    return {e: d.get(e, 0) for e in ESTADOS_HUECO}
