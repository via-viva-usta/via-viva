"""Sincronización opcional con un servicio web gratuito (propuesta: Supabase). Local primero:

- SQLite en la Pi es la fuente de verdad. Sin internet todo funciona; la cola espera.
- Solo salen **eventos** (sin velocidad, sin vehículo, sin foto, sin etiqueta de quien manejaba) y **riesgo por tramo**
  (sin variables ni la marca "reportado", que viene de datos de la Alcaldía). Nada de fotos, video, trayectorias ni
  datos crudos de la Alcaldía. Los datos DEMO, SINTÉTICOS y simulados nunca salen.
- Cola `cola_envio` en SQLite con reintentos y espera exponencial (30 s, 1 min, 2 min, … hasta 1 h).
- Claves solo en el `.env` de la Pi: `SUPABASE_URL` y `SUPABASE_CLAVE` (clave secreta del proyecto). En Supabase las
  tablas tienen RLS de solo lectura pública: con la clave pública nadie escribe (`viaviva/supabase_esquema.sql`).
  Sin claves, la sincronización queda apagada y solo se llena la cola local.
- La Pi es el punto de acceso WiFi (sin internet). Para sincronizar: cable de red o USB al celular con datos.

Uso: corre como hilo dentro de `pi.servidor`; para probar a mano: `python -m viaviva.sincronizacion --una-vez`.
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

from viaviva.almacen import conectar

TABLAS = {"eventos": "eventos_publicos", "huecos": "huecos_publicos", "riesgo": "riesgo_publico"}
INSTANCIA = os.getenv("VIAVIVA_INSTANCIA") or os.getenv("PI_ID_NODO", "pi-01")   # distingue la base de la Pi y la del PC
LOTE = 200
ESPERA_MIN_S, ESPERA_MAX_S = 30, 3600
EDAD_MIN_EVENTO_S = 60          # deja tiempo a que llegue la etiqueta del copiloto (± 3 s) antes de enviar


def _ahora() -> datetime:
    return datetime.now(UTC)


def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def es_demo(texto) -> bool:
    t = (texto or "").upper()
    return "DEMO" in t or "SINTETICO" in t or "SINTÉTICO" in t


def evento_publico(fila: dict) -> dict:
    """Lista blanca de columnas: lo que no está aquí no sale de la Pi."""
    return {"id_origen": f"{fila['id_nodo']}|{fila['ts_utc']}", "ts_utc": fila["ts_utc"],
            "lat": round(fila["lat"], 5), "lon": round(fila["lon"], 5), "clase": fila["clase"],
            "etiquetado": fila.get("etiqueta_manual") is not None, "id_tramo": fila.get("id_tramo"),
            "geohash7": fila.get("geohash7"), "origen": fila["origen"], "modelo_version": fila.get("modelo_version")}


def hueco_publico(fila: dict) -> dict:
    """Hueco = eventos agrupados (≤ 10 m) con su estado. Sin usuario ni nota (texto libre)."""
    return {"id_origen": f"{INSTANCIA}|{fila['id_hueco']}", "instancia": INSTANCIA, "id_local": fila["id_hueco"],
            "lat": round(fila["lat"], 5), "lon": round(fila["lon"], 5), "clase": fila["clase"],
            "n_detecciones": fila["n_detecciones"], "primera_ts": fila["primera_ts"], "ultima_ts": fila["ultima_ts"],
            "estado": fila["estado"], "ts_estado": fila.get("ts_estado"), "id_tramo": fila.get("id_tramo"),
            "severidad": fila.get("severidad"),
            "geohash7": fila.get("geohash7")}


def riesgo_publico(fila: dict) -> dict:
    return {"id_origen": f"{fila['modelo']}|{fila['version_modelo']}|{fila['fecha_calculo']}|{fila['id_tramo']}",
            "id_tramo": fila["id_tramo"], "modelo": fila["modelo"], "version_modelo": fila["version_modelo"],
            "fecha_calculo": fila["fecha_calculo"], "probabilidad": round(fila["probabilidad"], 4),
            "rango": fila.get("rango")}


def id_local_de(cambio: dict) -> int | None:
    """El id del hueco en esta base, sacado de `id_origen` («instancia|id»). None si es de otra instancia o si
    `instancia` / `id_local` del pedido no coinciden con `id_origen`."""
    instancia, _, local = str(cambio.get("id_origen") or "").rpartition("|")
    if instancia != INSTANCIA or not local.isdigit():
        return None
    if cambio.get("instancia", instancia) != instancia or str(cambio.get("id_local", local)) != local:
        return None
    return int(local)


class Sincronizador:
    def __init__(self, url: str | None = None, clave: str | None = None, url_db: str | None = None):
        self.url = (url if url is not None else os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.clave = clave if clave is not None else os.getenv("SUPABASE_CLAVE", "")
        self.url_db = url_db
        self.ultimo_error: str | None = None
        self.ultima_ok: str | None = None
        self.enviados_sesion = 0

    @property
    def configurado(self) -> bool:
        return bool(self.url and self.clave)

    # ---------------------------------------------------------------- cola
    def _marca(self, con, tabla: str) -> int:
        f = con.execute("SELECT ultimo_id FROM sync_marcas WHERE tabla = ?", (tabla,)).fetchone()
        return f[0] if f else 0

    def _poner_marca(self, con, tabla: str, ultimo: int) -> None:
        con.execute("INSERT INTO sync_marcas (tabla, ultimo_id) VALUES (?, ?) "
                    "ON CONFLICT (tabla) DO UPDATE SET ultimo_id = excluded.ultimo_id", (tabla, ultimo))

    def encolar_nuevos(self, con) -> int:
        """Pasa a la cola lo nuevo de eventos y riesgo (por id creciente; los DEMO se saltan pero avanzan la marca)."""
        n = 0
        limite = _iso(_ahora() - timedelta(seconds=EDAD_MIN_EVENTO_S))
        marca = self._marca(con, "eventos")
        ultimo = marca
        for f in _filas(con, "SELECT * FROM eventos WHERE id_evento > ? AND ts_carga <= ? ORDER BY id_evento",
                        (marca, limite)):
            ultimo = f["id_evento"]
            if f["origen"] == "simulado" or es_demo(f["id_nodo"]) or es_demo(f.get("modelo_version")):
                continue
            con.execute("INSERT INTO cola_envio (tabla, carga_json, creado) VALUES (?, ?, ?)",
                        ("eventos", json.dumps(evento_publico(f)), _iso(_ahora())))
            n += 1
        self._poner_marca(con, "eventos", ultimo)
        marca = self._marca(con, "riesgo")
        ultimo = marca
        for f in _filas(con, "SELECT * FROM riesgo WHERE id_riesgo > ? ORDER BY id_riesgo", (marca,)):
            ultimo = f["id_riesgo"]
            if es_demo(f["version_modelo"]) or es_demo(f.get("fuente_etiquetas")):
                continue
            con.execute("INSERT INTO cola_envio (tabla, carga_json, creado) VALUES (?, ?, ?)",
                        ("riesgo", json.dumps(riesgo_publico(f)), _iso(_ahora())))
            n += 1
        self._poner_marca(con, "riesgo", ultimo)
        # huecos: se reenvían cuando cambian (nueva detección o estado); la marca es la hora del último barrido
        desde = _iso(datetime.fromtimestamp(self._marca(con, "huecos"), UTC))
        barrido = int(_ahora().timestamp())
        for f in _filas(con, "SELECT * FROM huecos WHERE simulado = 0 AND (ts_carga >= ? OR ultima_ts >= ? OR "
                             "COALESCE(ts_estado, '') >= ?)", (desde, desde, desde)):
            con.execute("INSERT INTO cola_envio (tabla, carga_json, creado) VALUES (?, ?, ?)",
                        ("huecos", json.dumps(hueco_publico(f)), _iso(_ahora())))
            n += 1
        self._poner_marca(con, "huecos", barrido)
        con.commit()
        return n

    # ---------------------------------------------------------------- envío
    def _post(self, tabla_remota: str, filas: list[dict]) -> None:
        req = urllib.request.Request(
            f"{self.url}/rest/v1/{tabla_remota}?on_conflict=id_origen", data=json.dumps(filas).encode(),
            method="POST", headers={"apikey": self.clave, "Authorization": f"Bearer {self.clave}",
                                    "Content-Type": "application/json",
                                    "Prefer": "resolution=merge-duplicates,return=minimal"})
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status >= 300:
                raise urllib.error.HTTPError(req.full_url, r.status, "respuesta inesperada", r.headers, None)

    def enviar_pendientes(self, con) -> int:
        enviados = 0
        ahora = _iso(_ahora())
        for tabla, remota in TABLAS.items():
            while True:
                filas = con.execute("SELECT id, carga_json, intentos FROM cola_envio WHERE tabla = ? AND "
                                    "proximo_intento <= ? ORDER BY id LIMIT ?", (tabla, ahora, LOTE)).fetchall()
                if not filas:
                    break
                try:
                    self._post(remota, [json.loads(c) for _, c, _ in filas])
                except Exception as err:
                    self.ultimo_error = f"{_iso(_ahora())} {type(err).__name__}: {err}"[:200]
                    for i, _, intentos in filas:
                        espera = min(ESPERA_MAX_S, ESPERA_MIN_S * 2 ** intentos)
                        con.execute("UPDATE cola_envio SET intentos = intentos + 1, proximo_intento = ?, error = ? "
                                    "WHERE id = ?", (_iso(_ahora() + timedelta(seconds=espera)),
                                                     self.ultimo_error, i))
                    con.commit()
                    return enviados                  # sin red: no insistir con las otras tablas en esta vuelta
                con.executemany("DELETE FROM cola_envio WHERE id = ?", [(i,) for i, _, _ in filas])
                con.execute("UPDATE sync_marcas SET enviados = enviados + ? WHERE tabla = ?", (len(filas), tabla))
                con.commit()
                enviados += len(filas)
                self.ultima_ok = _iso(_ahora())
        self.enviados_sesion += enviados
        return enviados

    # ---------------------------------------------------------------- cambios hechos en el tablero en línea
    def _json(self, metodo: str, ruta: str, datos=None):
        req = urllib.request.Request(f"{self.url}/rest/v1/{ruta}", method=metodo,
                                     data=None if datos is None else json.dumps(datos).encode(),
                                     headers={"apikey": self.clave, "Authorization": f"Bearer {self.clave}",
                                              "Content-Type": "application/json", "Prefer": "return=minimal"})
        with urllib.request.urlopen(req, timeout=15) as r:
            cuerpo = r.read()
        return json.loads(cuerpo) if cuerpo else None

    def traer_cambios(self, con) -> int:
        """Los editores cambian estados en línea → tabla cambios_remotos. La Pi (fuente de verdad) los aplica a
        SQLite con el historial (usuario `nube:<correo>`) y los marca como aplicados. Los ajenos se ignoran.
        El hueco sale de `id_origen` (llave hacia huecos_publicos); si `id_local` o `instancia` no coinciden con
        él, el pedido se rechaza: así un pedido armado a mano no cambia otro hueco."""
        pendientes = self._json("GET", f"cambios_remotos?aplicado=eq.false&instancia=eq.{INSTANCIA}"
                                       "&select=id,id_origen,instancia,id_local,estado,nota,autor&order=id") or []
        from viaviva.almacen import cambiar_estado_hueco
        aplicados = 0
        for c in pendientes:
            id_hueco = id_local_de(c)
            try:
                ok = id_hueco is not None and cambiar_estado_hueco(
                    con, id_hueco, c["estado"], f"nube:{c.get('autor') or '?'}", nota=c.get("nota"))
            except ValueError:
                ok = False
            self._json("PATCH", f"cambios_remotos?id=eq.{int(c['id'])}",
                       {"aplicado": True, "resultado": "aplicado" if ok else "rechazado"})
            aplicados += ok
        return aplicados

    def una_vez(self) -> dict:
        con = conectar(self.url_db)
        try:
            encolados = self.encolar_nuevos(con)
            enviados = self.enviar_pendientes(con) if self.configurado else 0
            traidos = 0
            if self.configurado:
                try:
                    traidos = self.traer_cambios(con)
                except Exception as err:
                    self.ultimo_error = f"{_iso(_ahora())} cambios en línea: {type(err).__name__}: {err}"[:200]
            return {"encolados": encolados, "enviados": enviados, "cambios_en_linea": traidos, **self.estado(con)}
        finally:
            con.close()

    def estado(self, con=None) -> dict:
        propia = con is None
        con = con or conectar(self.url_db)
        try:
            pend = dict(con.execute("SELECT tabla, COUNT(*) FROM cola_envio GROUP BY tabla").fetchall())
            env = dict(con.execute("SELECT tabla, enviados FROM sync_marcas").fetchall())
        finally:
            if propia:
                con.close()
        return {"configurado": self.configurado, "pendientes": pend, "enviados_total": env,
                "ultima_ok": self.ultima_ok, "ultimo_error": self.ultimo_error}

    def bucle(self, parar: threading.Event, periodo_s: float = 30.0) -> None:
        while not parar.wait(periodo_s):
            try:
                self.una_vez()
            except Exception as err:
                self.ultimo_error = f"{_iso(_ahora())} {type(err).__name__}: {err}"[:200]


def _filas(con, sql: str, params=()) -> list[dict]:
    cur = con.execute(sql, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, f)) for f in cur.fetchall()]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--una-vez", action="store_true", help="encolar y enviar una vez y salir")
    a = ap.parse_args()
    s = Sincronizador()
    if not s.configurado:
        print("Sin SUPABASE_URL / SUPABASE_CLAVE en .env: solo se encola (nada sale de la Pi).")
    if a.una_vez:
        print(json.dumps(s.una_vez(), ensure_ascii=False, indent=1))
    else:
        s.bucle(threading.Event())


if __name__ == "__main__":
    main()
