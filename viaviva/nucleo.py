"""Núcleo de VÍA VIVA: recibe muestras de cualquier fuente (phyphox en vivo, sensores de la Pi o reproducción),
detecta, graba la sesión y guarda etiquetas, destellos de sincronía y eventos. Las páginas web solo leen `estado()`.

Sesión = carpeta `sesion_AAAA-MM-DD_hhmm[_nombre]/` (fuera de Git, en 06_CAMPO/sesiones):
  Accelerometer.csv, Gyroscope.csv, Location.csv, meta/time.csv  → MISMO formato del export de phyphox para iOS
      (+ 1 columna "UTC PC (s)": hora UTC del PC de cada muestra), así validar_campo, etl.recorridos, analysis/ y el
      modo reproducir las leen sin cambios
  etiquetas.csv (bitácora de marcas, incluye las deshechas) · <carpeta>_etiquetas.csv (solo las vigentes, t_s y clase)
  eventos.csv · destellos.csv · bitacora.jsonl · sesion.sqlite (etiquetas, eventos y destellos, a prueba de cortes)
  RESUMEN.md + resumen.json al cerrar (viaviva/resumen.py)
Nada se pierde si se cierra de golpe: las marcas se escriben y confirman al instante; las muestras se vacían cada 1 s.
"""
from __future__ import annotations

import csv
import json
import math
import os
import queue
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from viaviva import config
from viaviva.config import ParametrosUmbral
from viaviva.estructuras import BuferCircular

G = 9.81
CLASES_MARCA = [c for _, c, _ in config.ETIQUETAS]
CLASES_ETIQUETA = set(CLASES_MARCA) | {"impacto_fuerte", "otro", "parada"}
CLASES_EVENTO_DB = {"hueco", "resalto", "impacto_fuerte", "obstaculo"}   # las que acepta la tabla eventos

ARCHIVOS = {   # clave → (archivo, encabezado). Los 3 primeros como los escribe phyphox en iOS (+ UTC del PC)
    "acc": ("Accelerometer.csv", ["Time (s)", "X (m/s^2)", "Y (m/s^2)", "Z (m/s^2)", "UTC PC (s)"]),
    "giro": ("Gyroscope.csv", ["Time (s)", "X (rad/s)", "Y (rad/s)", "Z (rad/s)", "UTC PC (s)"]),
    "gps": ("Location.csv", ["Time (s)", "Latitude (°)", "Longitude (°)", "Height (m)", "Velocity (m/s)",
                             "Direction (°)", "Horizontal Accuracy (m)", "Vertical Accuracy (°)", "UTC PC (s)"]),
    "acc_mpu": ("Accelerometer_mpu6050.csv", ["Time (s)", "X (m/s^2)", "Y (m/s^2)", "Z (m/s^2)"]),
    "acc2": ("Accelerometer_adxl2.csv", ["Time (s)", "X (m/s^2)", "Y (m/s^2)", "Z (m/s^2)"]),
    "distancia": ("Distancia_vl53l0x.csv", ["Time (s)", "distancia_mm"]),
    "ambiente": ("Ambiente.csv", ["Time (s)", "temperatura_c", "humedad_pct", "lux", "sensor"]),
    "eventos": ("eventos.csv", ["t_s", "ts_utc", "p2p_g", "razon", "lat", "lon", "vel_kmh", "id_tramo", "clase",
                                "severidad", "confianza"]),
    "destellos": ("destellos.csv", ["t_s", "utc", "hora_local", "origen", "nota"]),
}
COL_ETIQUETAS = ["id", "t_s", "utc", "hora_local", "clase", "lat", "lon", "vel_kmh", "origen", "retardo_s", "anula_id"]


def _f(v) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return ""
    if isinstance(v, float):
        return f"{v:.9E}"
    return str(v)


_PARAMS: dict | None = None


def _parametros_detector() -> dict:
    global _PARAMS
    if _PARAMS is None:
        _PARAMS = {'v_min_kmh': 5, 'v_ref_kmh': 20, 'exponente_velocidad': 0.5, 'severidad_media_g': 0.6,
                   'severidad_alta_g': 1.0}
        try:
            import yaml
            for nombre in ('detector_calibrado.yaml', 'detector.yaml'):
                ruta = config.RAIZ / 'config' / nombre
                if ruta.exists():
                    _PARAMS.update({k: v for k, v in yaml.safe_load(ruta.read_text(encoding='utf-8')).items()
                                    if k in _PARAMS})
                    break
        except ImportError:
            pass
    return _PARAMS


def _utc(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class Welford:
    """Media y desviación en línea (una pasada, memoria O(1)) para R7."""

    def __init__(self):
        self.n, self.media, self._m2 = 0, 0.0, 0.0
        self.minimo, self.maximo = math.inf, -math.inf

    def agregar(self, x: float) -> None:
        self.n += 1
        d = x - self.media
        self.media += d / self.n
        self._m2 += d * (x - self.media)
        self.minimo, self.maximo = min(self.minimo, x), max(self.maximo, x)

    @property
    def desv(self) -> float:
        return math.sqrt(self._m2 / (self.n - 1)) if self.n > 1 else 0.0

    def resumen(self, decimales: int = 3) -> dict:
        r = lambda v: None if math.isinf(v) else round(v, decimales)
        return {"n": self.n, "media": round(self.media, decimales), "desv": round(self.desv, decimales),
                "min": r(self.minimo), "max": r(self.maximo)}


class Detector:
    """Detector por umbrales muestra a muestra (línea base, igual a `analysis/detector_umbral.py`).
    La ventana pico a pico vive en un BuferCircular (memoria fija). El detector calibrable con severidad y
    confianza está en `viaviva/detector.py`."""

    def __init__(self, fs: float, p: ParametrosUmbral | None = None):
        self.p = p or ParametrosUmbral()
        self.ventana: BuferCircular[float] = BuferCircular(int(min(64, max(2, round(self.p.ventana_p2p_s * fs)))))
        self.alfa = 1.0 / (self.p.tau_base_s * fs)
        self.calentamiento = int(self.p.tau_base_s * fs)
        self.refractario = int(self.p.refractario_s * fs)
        self.ms2, self.n, self.ultimo = 0.0, 0, None
        self.rms_disparo = 0.0

    def muestra(self, a_g: float, vel_kmh: float) -> float | None:
        self.ventana.agregar(a_g)
        p2p = max(self.ventana) - min(self.ventana)
        rms_ant = math.sqrt(self.ms2)
        disparo = (self.n >= self.calentamiento and vel_kmh > self.p.v_min_kmh and p2p > self.p.k_rel * rms_ant
                   and p2p > self.p.p2p_min_g and (self.ultimo is None or self.n - self.ultimo >= self.refractario))
        if disparo:
            self.ultimo, self.rms_disparo = self.n, rms_ant
        self.ms2 += self.alfa * (a_g * a_g - self.ms2)
        self.n += 1
        return p2p if disparo else None


class Sesion:
    """Una grabación. Escribe con búfer y vacía cada `vaciar_s` (la microSD sufre con escrituras pequeñas);
    las marcas van a sesion.sqlite con commit inmediato; `cerrar()` hace fsync."""

    def __init__(self, carpeta: Path, inicio_epoch: float, vaciar_s: float = 1.0):
        self.carpeta = carpeta
        self.vaciar_s = vaciar_s
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "meta").mkdir(exist_ok=True)
        self.f = {}
        for clave, (nombre, enc) in ARCHIVOS.items():
            fh = open(carpeta / nombre, "w", encoding="utf-8", newline="", buffering=64 * 1024)
            fh.write(",".join(f'"{c}"' for c in enc) + "\n")
            self.f[clave] = fh
        self.f_etq = open(carpeta / "etiquetas.csv", "w", encoding="utf-8", newline="")
        csv.writer(self.f_etq).writerow(COL_ETIQUETAS)
        self.f_bit = open(carpeta / "bitacora.jsonl", "a", encoding="utf-8")
        texto = datetime.fromtimestamp(inicio_epoch).astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        (carpeta / "meta" / "time.csv").write_text(
            '"event","experiment time","system time","system time text"\n'
            f'"START",{0.0:.15E},{inicio_epoch:.6f},"{texto} UTC-05:00"\n', encoding="utf-8")
        self.db = sqlite3.connect(carpeta / "sesion.sqlite", check_same_thread=False)
        self.db.executescript(
            "PRAGMA journal_mode=WAL;"
            "CREATE TABLE IF NOT EXISTS etiquetas (id INTEGER PRIMARY KEY, t_s REAL, utc TEXT, clase TEXT, lat REAL,"
            " lon REAL, vel_kmh REAL, origen TEXT, retardo_s REAL, anulada INTEGER NOT NULL DEFAULT 0);"
            "CREATE TABLE IF NOT EXISTS eventos (t_s REAL PRIMARY KEY, utc TEXT, p2p_g REAL, lat REAL, lon REAL,"
            " vel_kmh REAL, id_tramo INTEGER, clase TEXT, etiqueta TEXT);"
            "CREATE TABLE IF NOT EXISTS destellos (t_s REAL, utc TEXT, origen TEXT, nota TEXT);")
        self.ultimo_vaciado = time.monotonic()

    def fila(self, clave: str, valores) -> None:
        self.f[clave].write(",".join(_f(v) for v in valores) + "\n")

    def bitacora(self, registro: dict) -> None:
        self.f_bit.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")
        self.f_bit.flush()

    def etiqueta(self, e: dict) -> None:
        csv.writer(self.f_etq).writerow([e.get(c) for c in COL_ETIQUETAS])
        self.f_etq.flush()
        if e["anula_id"] is None:
            self.db.execute("INSERT INTO etiquetas (id, t_s, utc, clase, lat, lon, vel_kmh, origen, retardo_s) "
                            "VALUES (?,?,?,?,?,?,?,?,?)", (e["id"], e["t_s"], e["utc"], e["clase"], e["lat"], e["lon"],
                                                            e["vel_kmh"], e["origen"], e["retardo_s"]))
        else:
            self.db.execute("UPDATE etiquetas SET anulada = 1 WHERE id = ?", (e["anula_id"],))
        self.db.commit()
        self._etiquetas_vigentes()

    def _etiquetas_vigentes(self) -> None:
        """`<carpeta>_etiquetas.csv` (t_s, clase): el formato que lee etl.recorridos. Se rehace en cada cambio."""
        filas = self.db.execute("SELECT t_s, clase FROM etiquetas WHERE anulada = 0 ORDER BY t_s").fetchall()
        destino = self.carpeta.parent / f"{self.carpeta.name}_etiquetas.csv"
        tmp = destino.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["t_s", "clase"])
            w.writerows((round(t, 2), c) for t, c in filas)
        os.replace(tmp, destino)

    def evento(self, e: dict, t_rel: float) -> None:
        self.db.execute("INSERT OR REPLACE INTO eventos VALUES (?,?,?,?,?,?,?,?,?)",
                        (t_rel, e["ts_utc"], e["p2p_g"], e["lat"], e["lon"], e["vel_kmh"], e["id_tramo"], e["clase"],
                         e["etiqueta_manual"]))
        self.db.commit()

    def destello(self, d: dict) -> None:
        self.fila("destellos", (d["t_s"], d["utc"], d["hora_local"], d["origen"], d.get("nota") or ""))
        self.f["destellos"].flush()
        self.db.execute("INSERT INTO destellos VALUES (?,?,?,?)", (d["t_s"], d["utc"], d["origen"], d.get("nota")))
        self.db.commit()

    def vaciar_si_toca(self) -> None:
        if time.monotonic() - self.ultimo_vaciado >= self.vaciar_s:
            for fh in self.f.values():
                fh.flush()
            self.ultimo_vaciado = time.monotonic()

    def cerrar(self) -> None:
        for fh in [*self.f.values(), self.f_etq, self.f_bit]:
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
            fh.close()
        self.db.close()


class Nucleo:
    """Estado compartido. Las fuentes llaman a `acc`, `giro`, `gps`, `ambiente`, `distancia` desde sus hilos;
    la web llama a `estado`, `iniciar_grabacion`, `detener_grabacion`, `etiquetar`, `deshacer` y `destello`."""

    def __init__(self, fs_acc: float, origen: str = "nodo", id_nodo: str | None = None,
                 dir_grabaciones: Path | None = None, guardar_eventos=None, ajustar_tramo=None,
                 retardo_s: float | None = None, vaciar_s: float = 1.0):
        self.fs = fs_acc
        self.origen = origen                       # 'nodo' (sensores/phyphox en vivo) o 'simulado' (reproducción)
        self.id_nodo = id_nodo or config.ID_NODO
        self.dir_grabaciones = Path(dir_grabaciones or config.DIR_GRABACIONES)
        self.guardar_eventos = guardar_eventos     # función(lista, id_nodo, origen) → escribe en SQLite
        self.ajustar_tramo = ajustar_tramo         # función(lat, lon) → (id_tramo | None, distancia_m)
        self.retardo_s = config.RETARDO_REACCION_S if retardo_s is None else retardo_s
        self.vaciar_s = vaciar_s
        self.candado = threading.RLock()
        self.det = Detector(fs_acc)
        self.serie: BuferCircular[tuple] = BuferCircular(600)        # (t, |a|−1 g) a 20 Hz: 30 s
        self.trayecto: BuferCircular[tuple] = BuferCircular(1200)    # solo en memoria, para el mapa en vivo
        self.eventos: BuferCircular[dict] = BuferCircular(200)
        self.etiquetas: BuferCircular[dict] = BuferCircular(200)
        self.mensajes: BuferCircular[str] = BuferCircular(10)
        self.latencias = {k: Welford() for k in ("lectura_fifo_ms", "irq_a_lectura_ms", "detector_us", "ciclo_i2c_ms",
                                                 "http_phyphox_ms", "lote_a_pantalla_ms")}
        self.sensores: dict = {}                   # nombre → objeto con .estado() → dict
        self.sesion: Sesion | None = None
        self.t0_sesion = 0.0
        self.base_epoch = time.time()              # epoch de t = 0 de la fuente (lo corrige el GPS)
        self.hora_de_gps = False
        self.ultimo_t, self.mono_ultimo = 0.0, time.monotonic()
        self.n_acc, self.n_eventos_total, self.n_eventos_sin_gps = 0, 0, 0
        self.n_cortes, self.s_perdidos, self.reconexiones = 0, 0.0, 0
        self.lat = self.lon = self.precision = math.nan
        self.vel_kmh, self.vel_max_kmh, self.n_sat, self.fix = 0.0, 0.0, 0, False
        self.amb: dict = {}
        self.distancia_mm = math.nan
        self.parada_abierta = False
        self.id_etiqueta = 0
        self.destellos: list[dict] = []
        self.conectado = True
        self.al_cerrar_sesion = None               # función(carpeta) → p. ej. generar RESUMEN.md
        self._pendientes: queue.Queue = queue.Queue()
        threading.Thread(target=self._escritor, daemon=True, name="escritor-db").start()

    # ---------------------------------------------------------------- tiempo y bitácora
    def t_ahora(self) -> float:
        return self.ultimo_t + (time.monotonic() - self.mono_ultimo if self.conectado else 0.0)

    def epoch(self, t: float) -> float:
        return self.base_epoch + t

    def ts_utc(self, t: float) -> str:
        return _utc(self.epoch(t))

    def aviso(self, texto: str, tipo: str = "aviso", **datos) -> None:
        self.mensajes.agregar(f"{datetime.now():%H:%M:%S} {texto}")
        self.bitacora(tipo, texto=texto, **datos)

    def bitacora(self, tipo: str, **datos) -> None:
        if self.sesion:
            self.sesion.bitacora({"utc": _utc(time.time()), "tipo": tipo, **datos})

    # ---------------------------------------------------------------- entradas de las fuentes
    def acc(self, filas, recibido_epoch: float | None = None) -> None:
        """filas = [(t_s, ax, ay, az)] en m/s² (con la gravedad), en orden. `recibido_epoch` = hora del PC en que
        llegó el lote (la última fila); si falta, la hora sale de base_epoch."""
        if not filas:
            return
        t_lote0 = time.perf_counter()
        nuevos = []
        with self.candado:
            umbral_corte = 1.5 / self.fs
            for t, x, y, z in filas:
                if self.n_acc and t - self.ultimo_t > umbral_corte:     # muestras que no llegaron
                    hueco = t - self.ultimo_t - 1.0 / self.fs
                    self.n_cortes += 1
                    self.s_perdidos += hueco
                    if hueco > 0.5:
                        self.bitacora("perdida", t_s=round(self.ultimo_t, 3), segundos=round(hueco, 3))
                a = math.sqrt(x * x + y * y + z * z) / G - 1.0
                t0 = time.perf_counter()
                p2p = self.det.muestra(a, self.vel_kmh)
                self.latencias["detector_us"].agregar((time.perf_counter() - t0) * 1e6)
                if p2p is not None:
                    nuevos.append(self._nuevo_evento(t, p2p))
                if self.n_acc % max(1, round(self.fs / 20)) == 0:
                    self.serie.agregar((round(t, 2), round(a, 3)))
                self.n_acc += 1
                self.ultimo_t = t
                if self.sesion:
                    utc = (recibido_epoch - (filas[-1][0] - t)) if recibido_epoch else self.epoch(t)
                    self.sesion.fila("acc", (t - self.t0_sesion, x, y, z, round(utc, 3)))
            self.mono_ultimo = time.monotonic()
            if self.sesion:
                self.sesion.vaciar_si_toca()
        self.latencias["lote_a_pantalla_ms"].agregar((time.perf_counter() - t_lote0) * 1e3)
        for e in nuevos:
            if self.sesion and e["lat"] is not None:
                self._pendientes.put(e)

    def giro(self, filas, recibido_epoch: float | None = None) -> None:
        with self.candado:
            if self.sesion:
                for t, x, y, z in filas:
                    utc = (recibido_epoch - (filas[-1][0] - t)) if recibido_epoch else self.epoch(t)
                    self.sesion.fila("giro", (t - self.t0_sesion, x, y, z, round(utc, 3)))

    def acc2(self, filas) -> None:
        with self.candado:
            if self.sesion:
                for t, x, y, z in filas:
                    self.sesion.fila("acc2", (t - self.t0_sesion, x, y, z))

    def acc_mpu(self, filas) -> None:
        with self.candado:
            if self.sesion:
                for t, x, y, z in filas:
                    self.sesion.fila("acc_mpu", (t - self.t0_sesion, x, y, z))

    def gps(self, t: float, lat: float, lon: float, alt: float = math.nan, vel_ms: float = math.nan,
            rumbo: float = math.nan, precision_m: float = math.nan, n_sat: int = 0, utc_epoch: float | None = None,
            recibido_epoch: float | None = None):
        with self.candado:
            self.fix = not (math.isnan(lat) or math.isnan(lon))
            if self.fix:
                self.lat, self.lon, self.precision = lat, lon, precision_m
                self.trayecto.agregar((round(lat, 6), round(lon, 6)))
            self.vel_kmh = 0.0 if math.isnan(vel_ms) or vel_ms < 0 else vel_ms * 3.6
            if self.sesion:
                self.vel_max_kmh = max(self.vel_max_kmh, self.vel_kmh)
            self.n_sat = n_sat
            if utc_epoch is not None:              # la Pi no tiene reloj con pila: manda la hora del GPS
                nueva = utc_epoch - t
                if not self.hora_de_gps or abs(nueva - self.base_epoch) > 2.0:
                    if abs(nueva - self.base_epoch) > 2.0:
                        self.aviso(f"Hora corregida con el GPS ({nueva - self.base_epoch:+.0f} s)")
                    self.base_epoch, self.hora_de_gps = nueva, True
            if self.sesion:
                utc = recibido_epoch if recibido_epoch else self.epoch(t)
                self.sesion.fila("gps", (t - self.t0_sesion, lat, lon, alt, vel_ms, rumbo, precision_m, math.nan,
                                         round(utc, 3)))

    def ambiente(self, t: float, temperatura=None, humedad=None, lux=None, sensor: str = "") -> None:
        with self.candado:
            for k, v in (("temperatura_c", temperatura), ("humedad_pct", humedad), ("lux", lux)):
                if v is not None:
                    self.amb[k] = round(v, 1)
            if self.sesion:
                self.sesion.fila("ambiente", (t - self.t0_sesion, temperatura, humedad, lux, sensor))

    def distancia(self, t: float, mm: float) -> None:
        with self.candado:
            self.distancia_mm = mm
            if self.sesion:
                self.sesion.fila("distancia", (t - self.t0_sesion, mm))

    def conexion(self, conectado: bool, detalle: str = "") -> None:
        """La fuente avisa si se cortó o volvió (hotspot del iPhone)."""
        with self.candado:
            if conectado == self.conectado:
                return
            self.conectado = conectado
            if conectado:
                self.reconexiones += 1
                self.aviso(f"Conexión recuperada {detalle}".strip(), "reconexion")
            else:
                self.aviso(f"CONEXIÓN PERDIDA {detalle}".strip(), "corte")

    # ---------------------------------------------------------------- eventos y etiquetas
    def _nuevo_evento(self, t: float, p2p: float) -> dict:
        tiene_gps = self.fix
        id_tramo = None
        if tiene_gps and self.ajustar_tramo:
            id_tramo, _ = self.ajustar_tramo(self.lat, self.lon)
        sev, conf = self._severidad(p2p)
        e = {"t_s": round(t, 3), "ts_utc": self.ts_utc(t), "p2p_g": round(p2p, 3),
             "razon": round(p2p / self.det.rms_disparo, 1) if self.det.rms_disparo > 0 else None,
             "lat": round(self.lat, 7) if tiene_gps else None, "lon": round(self.lon, 7) if tiene_gps else None,
             "vel_kmh": round(self.vel_kmh, 1), "id_tramo": id_tramo, "clase": "impacto_fuerte",
             "etiqueta_manual": None, "id_etiqueta": None, "severidad": sev, "confianza": conf}
        # Clase provisional = impacto_fuerte (sin clasificar) hasta que alguien la etiquete a ± 3 s.
        for etq in self.etiquetas.ultimos(5):
            if (not etq.get("anulada") and abs(etq["t_abs"] - t) <= config.VENTANA_ETIQUETA_S
                    and etq["clase"] in CLASES_ETIQUETA - {"parada"}):
                self._aplicar_etiqueta(e, etq)
        self.eventos.agregar(e)
        self.n_eventos_total += 1
        if not tiene_gps:
            self.n_eventos_sin_gps += 1
        if self.sesion:
            t_rel = round(t - self.t0_sesion, 3)
            self.sesion.fila("eventos", (t_rel, e["ts_utc"], e["p2p_g"], e["razon"], e["lat"], e["lon"], e["vel_kmh"],
                                         id_tramo, e["clase"], sev, conf))
            self.sesion.evento(e, t_rel)
        return e

    def _severidad(self, p2p: float) -> tuple[str, float]:
        """Amplitud normalizada por velocidad = (p2p / 2) / (max(v, v_min) / v_ref) ** exp, con los cortes de
        config/detector.yaml. Confianza = cuánto supera el disparo al umbral de pico (1 − umbral/p2p)."""
        p = _parametros_detector()
        factor = (max(self.vel_kmh, p['v_min_kmh']) / p['v_ref_kmh']) ** p['exponente_velocidad']
        amp = (p2p / 2) / factor
        sev = 'alta' if amp >= p['severidad_alta_g'] else 'media' if amp >= p['severidad_media_g'] else 'baja'
        return sev, round(max(0.0, 1 - self.det.p.p2p_min_g / p2p), 3) if p2p > 0 else 0.0

    @staticmethod
    def _aplicar_etiqueta(e: dict, etq: dict) -> None:
        e["etiqueta_manual"], e["id_etiqueta"] = etq["clase"], etq["id"]
        e["clase"] = etq["clase"] if etq["clase"] in CLASES_EVENTO_DB else "impacto_fuerte"

    def etiquetar(self, clase: str, origen: str = "web", retardo_s: float | None = None) -> dict:
        if clase not in CLASES_ETIQUETA:
            raise ValueError(f"clase desconocida: {clase}")
        retardo = self.retardo_s if retardo_s is None else retardo_s
        with self.candado:
            if clase == "parada":
                clase = "parada_fin" if self.parada_abierta else "parada_inicio"
                self.parada_abierta = not self.parada_abierta
            t = self.t_ahora() + retardo
            self.id_etiqueta += 1
            e = {"id": self.id_etiqueta, "t_s": round(t - (self.t0_sesion if self.sesion else 0.0), 2),
                 "utc": self.ts_utc(t), "hora_local": datetime.now().astimezone().isoformat(timespec="milliseconds"),
                 "clase": clase, "lat": None if not self.fix else round(self.lat, 7),
                 "lon": None if not self.fix else round(self.lon, 7), "vel_kmh": round(self.vel_kmh, 1),
                 "origen": origen, "retardo_s": retardo, "anula_id": None}
            if self.sesion:
                self.sesion.etiqueta(e)
                self.bitacora("etiqueta", id=e["id"], clase=clase, t_s=e["t_s"], origen=origen)
            self.etiquetas.agregar({**e, "t_abs": t, "anulada": False})
            actualizados = []
            for ev in self.eventos.ultimos(5):
                if abs(ev["t_s"] - t) <= config.VENTANA_ETIQUETA_S and ev["etiqueta_manual"] is None:
                    self._aplicar_etiqueta(ev, e)
                    actualizados.append(ev)
        self._reguardar(actualizados)
        return e

    def deshacer(self, origen: str = "web") -> dict | None:
        """Anula la última marca vigente (tecla U). Queda en etiquetas.csv como fila con `anula_id`."""
        with self.candado:
            ultima = next((x for x in reversed(list(self.etiquetas)) if not x.get("anulada")
                           and x["anula_id"] is None), None)
            if ultima is None:
                return None
            ultima["anulada"] = True
            self.id_etiqueta += 1
            e = {"id": self.id_etiqueta, "t_s": ultima["t_s"], "utc": ultima["utc"],
                 "hora_local": datetime.now().astimezone().isoformat(timespec="milliseconds"), "clase": "deshacer",
                 "lat": None, "lon": None, "vel_kmh": None, "origen": origen, "retardo_s": None,
                 "anula_id": ultima["id"]}
            if self.sesion:
                self.sesion.etiqueta(e)
                self.bitacora("deshacer", anula_id=ultima["id"], clase=ultima["clase"])
            if ultima["clase"].startswith("parada_"):
                self.parada_abierta = not self.parada_abierta
            actualizados = []
            for ev in self.eventos.ultimos(10):
                if ev["id_etiqueta"] == ultima["id"]:
                    ev["etiqueta_manual"], ev["id_etiqueta"], ev["clase"] = None, None, "impacto_fuerte"
                    actualizados.append(ev)
        self._reguardar(actualizados)
        return {"anulada": ultima["id"], "clase": ultima["clase"]}

    def _reguardar(self, eventos) -> None:
        for ev in eventos:
            if self.sesion:
                self.sesion.evento(ev, round(ev["t_s"] - self.t0_sesion, 3))
                if ev["lat"] is not None:
                    self._pendientes.put(ev)      # la base hace UPSERT por (id_nodo, ts_utc)

    def destello(self, origen: str = "web", nota: str | None = None) -> dict:
        """Instante del destello de la página /sync (la cámara lo graba): sirve para alinear el video."""
        with self.candado:
            ahora = time.time()
            t = self.t_ahora()
            d = {"t_s": round(t - (self.t0_sesion if self.sesion else 0.0), 3), "utc": _utc(ahora),
                 "hora_local": datetime.now().astimezone().isoformat(timespec="milliseconds"), "origen": origen,
                 "nota": nota}
            self.destellos.append(d)
            if self.sesion:
                self.sesion.destello(d)
                self.bitacora("destello", **d)
        return d

    def _escritor(self) -> None:
        """Hilo aparte: la escritura en la base general nunca frena la adquisición."""
        while True:
            e = self._pendientes.get()
            lote = [e]
            while not self._pendientes.empty() and len(lote) < 50:
                lote.append(self._pendientes.get_nowait())
            if self.guardar_eventos:
                try:
                    self.guardar_eventos(lote, self.id_nodo, self.origen)
                except Exception as err:            # la base nunca debe tumbar la captura
                    self.aviso(f"No se pudo guardar en la base: {err}")

    def vaciar_pendientes(self, espera_s: float = 2.0) -> None:
        fin = time.monotonic() + espera_s
        while not self._pendientes.empty() and time.monotonic() < fin:
            time.sleep(0.02)
        time.sleep(0.05)

    # ---------------------------------------------------------------- grabación
    def iniciar_grabacion(self, nombre: str = "") -> str:
        with self.candado:
            if self.sesion:
                return self.sesion.carpeta.name
            limpio = "".join(c for c in nombre.lower().replace(" ", "_") if c.isalnum() or c in "_-")[:30]
            base = "sesion_" + datetime.now().strftime("%Y-%m-%d_%H%M") + (f"_{limpio}" if limpio else "")
            carpeta, k = self.dir_grabaciones / base, 2
            while carpeta.exists():
                carpeta, k = self.dir_grabaciones / f"{base}_{k}", k + 1
            self.t0_sesion = self.t_ahora()
            self.sesion = Sesion(carpeta, self.epoch(self.t0_sesion), self.vaciar_s)
            self.parada_abierta = False
            self.n_cortes, self.s_perdidos, self.vel_max_kmh = 0, 0.0, 0.0
            self.bitacora("inicio", carpeta=carpeta.name, origen=self.origen, id_nodo=self.id_nodo, fs_hz=self.fs,
                          retardo_s=self.retardo_s)
            self.aviso(f"Grabando en {carpeta.name}")
            return carpeta.name

    def detener_grabacion(self) -> str | None:
        with self.candado:
            if not self.sesion:
                return None
            carpeta = self.sesion.carpeta
            self.bitacora("fin", muestras=self.n_acc, cortes=self.n_cortes, s_perdidos=round(self.s_perdidos, 3),
                          reconexiones=self.reconexiones,
                          latencias={k: w.resumen() for k, w in self.latencias.items() if w.n})
            self.sesion.cerrar()
            self.sesion = None
            self.mensajes.agregar(f"{datetime.now():%H:%M:%S} Grabación guardada: {carpeta.name}")
        self.vaciar_pendientes()
        if self.al_cerrar_sesion:
            try:
                self.al_cerrar_sesion(carpeta)
            except Exception as err:
                self.mensajes.agregar(f"{datetime.now():%H:%M:%S} No se pudo hacer el RESUMEN: {err}")
        return carpeta.name

    # ---------------------------------------------------------------- estado para la web
    def estado(self) -> dict:
        with self.candado:
            sin_datos = time.monotonic() - self.mono_ultimo > 2.0
            vigentes = [x for x in self.etiquetas if not x.get("anulada") and x["anula_id"] is None]
            por_clase: dict[str, int] = {}
            if self.sesion:
                for x in vigentes:
                    if x["t_abs"] >= self.t0_sesion - 5:
                        por_clase[x["clase"]] = por_clase.get(x["clase"], 0) + 1
            return {
                "grabando": self.sesion is not None,
                "carpeta": self.sesion.carpeta.name if self.sesion else None,
                "t_grabacion_s": round(self.t_ahora() - self.t0_sesion, 1) if self.sesion else 0,
                "origen": self.origen, "id_nodo": self.id_nodo, "fs_hz": self.fs, "conectado": self.conectado,
                "acelerometro_sin_datos": sin_datos, "muestras": self.n_acc,
                "cortes": self.n_cortes, "s_perdidos": round(self.s_perdidos, 2), "reconexiones": self.reconexiones,
                "gps": {"fix": self.fix, "lat": None if math.isnan(self.lat) else self.lat,
                        "lon": None if math.isnan(self.lon) else self.lon,
                        "precision_m": None if math.isnan(self.precision) else round(self.precision, 1),
                        "vel_kmh": round(self.vel_kmh, 1), "vel_max_kmh": round(self.vel_max_kmh, 1),
                        "satelites": self.n_sat, "hora_de_gps": self.hora_de_gps},
                "ambiente": dict(self.amb),
                "distancia_mm": None if math.isnan(self.distancia_mm) else round(self.distancia_mm),
                "eventos": self.n_eventos_total, "eventos_sin_gps": self.n_eventos_sin_gps,
                "ultimos_eventos": [{k: v for k, v in x.items()} for x in self.eventos.ultimos(6)],
                "etiquetas": [{k: v for k, v in x.items() if k != "t_abs"} for x in self.etiquetas.ultimos(8)],
                "n_etiquetas": len(vigentes), "etiquetas_por_clase": por_clase,
                "destellos": len(self.destellos), "retardo_s": self.retardo_s,
                "serie": self.serie.ultimos(600), "trayecto": self.trayecto.ultimos(1200)[::3],
                "sensores": {n: s.estado() for n, s in self.sensores.items()},
                "latencias": {k: w.resumen() for k, w in self.latencias.items() if w.n},
                "mensajes": list(self.mensajes),
            }
