"""Núcleo de la Pi: recibe muestras de cualquier fuente (sensores reales, reproducción o simulación), detecta,
graba la sesión y guarda los eventos. La página web solo lee `estado()` y llama a grabar / etiquetar.

La grabación queda en el MISMO formato del export de phyphox para iOS (Accelerometer.csv en m/s², Gyroscope.csv,
Location.csv, meta/time.csv) + archivos propios del nodo. Así `herramientas.validar_campo`, `etl.recorridos`,
`analysis/` y el modo reproducir la leen sin cambios.
"""
from __future__ import annotations

import csv
import math
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from pi import config
from pi.config import ParametrosUmbral
from pi.estructuras import BuferCircular

G = 9.81
CLASES_ETIQUETA = {"hueco", "resalto", "grieta", "tapa", "obstaculo", "impacto_fuerte", "parche", "otro", "parada"}
CLASES_EVENTO_DB = {"hueco", "resalto", "impacto_fuerte", "obstaculo"}   # las que acepta la tabla eventos

ARCHIVOS = {   # nombre → encabezado (los 3 primeros como los escribe phyphox en iOS)
    "acc": ("Accelerometer.csv", ["Time (s)", "X (m/s^2)", "Y (m/s^2)", "Z (m/s^2)"]),
    "giro": ("Gyroscope.csv", ["Time (s)", "X (rad/s)", "Y (rad/s)", "Z (rad/s)"]),
    "gps": ("Location.csv", ["Time (s)", "Latitude (°)", "Longitude (°)", "Height (m)", "Velocity (m/s)",
                             "Direction (°)", "Horizontal Accuracy (m)", "Vertical Accuracy (°)"]),
    "acc_mpu": ("Accelerometer_mpu6050.csv", ["Time (s)", "X (m/s^2)", "Y (m/s^2)", "Z (m/s^2)"]),
    "distancia": ("Distancia_vl53l0x.csv", ["Time (s)", "distancia_mm"]),
    "ambiente": ("Ambiente.csv", ["Time (s)", "temperatura_c", "humedad_pct", "lux", "sensor"]),
    "eventos": ("eventos.csv", ["t_s", "ts_utc", "p2p_g", "razon", "lat", "lon", "vel_kmh", "id_tramo", "clase"]),
}


def _f(v) -> str:
    return "" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.9E}" if isinstance(v, float) else str(v)


class Welford:
    """Media y desviación en línea (una pasada, memoria O(1)): igual que `medir()` del firmware (R7)."""

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
    """Detector por umbrales muestra a muestra: mismo algoritmo y parámetros que `analysis/detector_umbral.py`,
    `herramientas/captura_phyphox_remoto.DetectorEnVivo` y `src/detector_umbral.h` del ESP32.
    La ventana pico a pico vive en un BuferCircular (memoria fija)."""

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
    """Una grabación: carpeta `data/raw/pi/AAAA-MM-DD_HHMM_nombre/` (fuera de Git). Escribe con búfer y vacía cada
    segundo (la microSD sufre con escrituras pequeñas); `cerrar()` hace fsync para no perder datos al apagar."""

    def __init__(self, carpeta: Path, inicio_epoch: float):
        self.carpeta = carpeta
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "meta").mkdir(exist_ok=True)
        self.f = {}
        for clave, (nombre, enc) in ARCHIVOS.items():
            fh = open(carpeta / nombre, "w", encoding="utf-8", newline="", buffering=64 * 1024)
            fh.write(",".join(f'"{c}"' for c in enc) + "\n")
            self.f[clave] = fh
        self.f_etq = open(carpeta / "etiquetas.csv", "w", encoding="utf-8", newline="")
        csv.writer(self.f_etq).writerow(["t_s", "hora_pc", "clase", "lat", "lon", "vel_kmh", "origen"])
        self.f_etq_corto = open(carpeta.parent / f"{carpeta.name}_etiquetas.csv", "w", encoding="utf-8", newline="")
        csv.writer(self.f_etq_corto).writerow(["t_s", "clase"])
        texto = datetime.fromtimestamp(inicio_epoch).astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        (carpeta / "meta" / "time.csv").write_text(
            '"event","experiment time","system time","system time text"\n'
            f'"START",{0.0:.15E},{inicio_epoch:.6f},"{texto} UTC-05:00"\n', encoding="utf-8")
        self.ultimo_vaciado = time.monotonic()

    def fila(self, clave: str, valores) -> None:
        self.f[clave].write(",".join(_f(v) for v in valores) + "\n")

    def etiqueta(self, e: dict) -> None:
        csv.writer(self.f_etq).writerow(e.values())
        csv.writer(self.f_etq_corto).writerow([e["t_s"], e["clase"]])
        self.f_etq.flush()
        self.f_etq_corto.flush()

    def vaciar_si_toca(self) -> None:
        if time.monotonic() - self.ultimo_vaciado >= 1.0:
            for fh in self.f.values():
                fh.flush()
            self.ultimo_vaciado = time.monotonic()

    def cerrar(self) -> None:
        import os
        for fh in [*self.f.values(), self.f_etq, self.f_etq_corto]:
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
            fh.close()


class Nucleo:
    """Estado compartido. Las fuentes llaman a `acc`, `giro`, `gps`, `ambiente`, `distancia` desde sus hilos;
    el servidor web llama a `estado`, `iniciar_grabacion`, `detener_grabacion` y `etiquetar`."""

    def __init__(self, fs_acc: float, origen: str = "nodo", id_nodo: str | None = None,
                 dir_grabaciones: Path | None = None, guardar_eventos=None, ajustar_tramo=None):
        self.fs = fs_acc
        self.origen = origen                       # 'nodo' (sensores) o 'simulado' (reproducción / prueba)
        self.id_nodo = id_nodo or config.ID_NODO
        self.dir_grabaciones = dir_grabaciones or config.DIR_GRABACIONES
        self.guardar_eventos = guardar_eventos     # función(lista de eventos) → None (escribe en SQLite)
        self.ajustar_tramo = ajustar_tramo         # función(lat, lon) → (id_tramo | None, distancia_m)
        self.candado = threading.RLock()
        self.det = Detector(fs_acc)
        self.serie: BuferCircular[tuple] = BuferCircular(600)        # (t, |a|−1 g) a 20 Hz: 30 s
        self.trayecto: BuferCircular[tuple] = BuferCircular(1200)    # solo en memoria, para el mapa en vivo
        self.eventos: BuferCircular[dict] = BuferCircular(200)
        self.etiquetas: BuferCircular[dict] = BuferCircular(200)
        self.mensajes: BuferCircular[str] = BuferCircular(10)
        self.latencias = {k: Welford() for k in ("lectura_fifo_ms", "irq_a_lectura_ms", "detector_us", "ciclo_i2c_ms")}
        self.sensores: dict = {}                   # nombre → objeto con .estado() → dict
        self.sesion: Sesion | None = None
        self.t0_sesion = 0.0
        self.base_epoch = time.time()              # epoch de t = 0 de la fuente (lo corrige el GPS)
        self.hora_de_gps = False
        self.ultimo_t, self.mono_ultimo = 0.0, time.monotonic()
        self.n_acc, self.n_eventos_total, self.n_eventos_sin_gps = 0, 0, 0
        self.lat = self.lon = self.precision = math.nan
        self.vel_kmh, self.n_sat, self.fix = 0.0, 0, False
        self.amb: dict = {}
        self.distancia_mm = math.nan
        self.parada_abierta = False
        self._pendientes: queue.Queue = queue.Queue()
        threading.Thread(target=self._escritor, daemon=True, name="escritor-db").start()

    # ---------------------------------------------------------------- tiempo
    def t_ahora(self) -> float:
        return self.ultimo_t + (time.monotonic() - self.mono_ultimo)

    def epoch(self, t: float) -> float:
        return self.base_epoch + t

    def ts_utc(self, t: float) -> str:
        return datetime.fromtimestamp(self.epoch(t), timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def aviso(self, texto: str) -> None:
        self.mensajes.agregar(f"{datetime.now():%H:%M:%S} {texto}")

    # ---------------------------------------------------------------- entradas de las fuentes
    def acc(self, filas) -> None:
        """filas = [(t_s, ax, ay, az)] en m/s² (con la gravedad), en orden."""
        if not filas:
            return
        nuevos = []
        with self.candado:
            for t, x, y, z in filas:
                a = math.sqrt(x * x + y * y + z * z) / G - 1.0
                t0 = time.perf_counter()
                p2p = self.det.muestra(a, self.vel_kmh)
                self.latencias["detector_us"].agregar((time.perf_counter() - t0) * 1e6)
                if p2p is not None:
                    nuevos.append(self._nuevo_evento(t, p2p))
                if self.n_acc % max(1, round(self.fs / 20)) == 0:
                    self.serie.agregar((round(t, 2), round(a, 3)))
                self.n_acc += 1
                if self.sesion:
                    self.sesion.fila("acc", (t - self.t0_sesion, x, y, z))
            self.ultimo_t, self.mono_ultimo = filas[-1][0], time.monotonic()
            if self.sesion:
                self.sesion.vaciar_si_toca()
        for e in nuevos:
            if self.sesion and e["lat"] is not None:
                self._pendientes.put(e)

    def giro(self, filas) -> None:
        with self.candado:
            if self.sesion:
                for t, x, y, z in filas:
                    self.sesion.fila("giro", (t - self.t0_sesion, x, y, z))

    def acc_mpu(self, filas) -> None:
        with self.candado:
            if self.sesion:
                for t, x, y, z in filas:
                    self.sesion.fila("acc_mpu", (t - self.t0_sesion, x, y, z))

    def gps(self, t: float, lat: float, lon: float, alt: float = math.nan, vel_ms: float = math.nan,
            rumbo: float = math.nan, precision_m: float = math.nan, n_sat: int = 0, utc_epoch: float | None = None):
        with self.candado:
            self.fix = not (math.isnan(lat) or math.isnan(lon))
            if self.fix:
                self.lat, self.lon, self.precision = lat, lon, precision_m
                self.trayecto.agregar((round(lat, 6), round(lon, 6)))
            self.vel_kmh = 0.0 if math.isnan(vel_ms) or vel_ms < 0 else vel_ms * 3.6
            self.n_sat = n_sat
            if utc_epoch is not None:              # la Pi no tiene reloj con pila: manda la hora del GPS
                nueva = utc_epoch - t
                if not self.hora_de_gps or abs(nueva - self.base_epoch) > 2.0:
                    if abs(nueva - self.base_epoch) > 2.0:
                        self.aviso(f"Hora corregida con el GPS ({nueva - self.base_epoch:+.0f} s)")
                    self.base_epoch, self.hora_de_gps = nueva, True
            if self.sesion:
                self.sesion.fila("gps", (t - self.t0_sesion, lat, lon, alt, vel_ms, rumbo, precision_m, math.nan))

    def ambiente(self, t: float, temperatura=None, humedad=None, lux=None, sensor: str = "") -> None:
        with self.candado:
            for k, v in (("temperatura_c", temperatura), ("humedad_pct", humedad), ("lux", lux)):
                if v is not None:
                    self.amb[k] = round(v, 1)
                    self.amb[k + "_t"] = t
            if self.sesion:
                self.sesion.fila("ambiente", (t - self.t0_sesion, temperatura, humedad, lux, sensor))

    def distancia(self, t: float, mm: float) -> None:
        with self.candado:
            self.distancia_mm = mm
            if self.sesion:
                self.sesion.fila("distancia", (t - self.t0_sesion, mm))

    # ---------------------------------------------------------------- eventos y etiquetas
    def _nuevo_evento(self, t: float, p2p: float) -> dict:
        tiene_gps = self.fix
        id_tramo = None
        if tiene_gps and self.ajustar_tramo:
            id_tramo, _ = self.ajustar_tramo(self.lat, self.lon)
        e = {"t_s": round(t, 3), "ts_utc": self.ts_utc(t), "p2p_g": round(p2p, 3),
             "razon": round(p2p / self.det.rms_disparo, 1) if self.det.rms_disparo > 0 else None,
             "lat": round(self.lat, 7) if tiene_gps else None, "lon": round(self.lon, 7) if tiene_gps else None,
             "vel_kmh": round(self.vel_kmh, 1), "id_tramo": id_tramo, "clase": "impacto_fuerte",
             "etiqueta_manual": None}
        # Clase provisional = impacto_fuerte (sin clasificar) hasta que alguien la etiquete a ± 3 s.
        for etq in self.etiquetas.ultimos(5):
            if abs(etq["t_s"] - t) <= config.VENTANA_ETIQUETA_S and etq["clase"] in CLASES_ETIQUETA - {"parada"}:
                self._aplicar_etiqueta(e, etq["clase"])
        self.eventos.agregar(e)
        self.n_eventos_total += 1
        if not tiene_gps:
            self.n_eventos_sin_gps += 1
        if self.sesion:
            self.sesion.fila("eventos", (round(t - self.t0_sesion, 3), e["ts_utc"], e["p2p_g"], e["razon"], e["lat"],
                                         e["lon"], e["vel_kmh"], id_tramo, e["clase"]))
        return e

    @staticmethod
    def _aplicar_etiqueta(e: dict, clase: str) -> None:
        e["etiqueta_manual"] = clase
        if clase in CLASES_EVENTO_DB:
            e["clase"] = clase

    def etiquetar(self, clase: str, origen: str = "web") -> dict:
        if clase not in CLASES_ETIQUETA:
            raise ValueError(f"clase desconocida: {clase}")
        with self.candado:
            if clase == "parada":
                clase = "parada_fin" if self.parada_abierta else "parada_inicio"
                self.parada_abierta = not self.parada_abierta
            t = self.t_ahora()
            e = {"t_s": round(t - (self.t0_sesion if self.sesion else 0.0), 2),
                 "hora_pc": datetime.now().astimezone().isoformat(timespec="milliseconds"), "clase": clase,
                 "lat": None if not self.fix else round(self.lat, 7), "lon": None if not self.fix else round(self.lon, 7),
                 "vel_kmh": round(self.vel_kmh, 1), "origen": origen}
            if self.sesion:
                self.sesion.etiqueta(e)
            self.etiquetas.agregar({**e, "t_s": round(t, 2)})
            actualizados = []
            if clase in CLASES_ETIQUETA:
                for ev in self.eventos.ultimos(5):
                    if abs(ev["t_s"] - t) <= config.VENTANA_ETIQUETA_S and ev["etiqueta_manual"] is None:
                        self._aplicar_etiqueta(ev, clase)
                        actualizados.append(ev)
        for ev in actualizados:
            if self.sesion and ev["lat"] is not None:
                self._pendientes.put(ev)              # la base hace UPSERT por (id_nodo, ts_utc)
        return e

    def _escritor(self) -> None:
        """Hilo aparte: la escritura en SQLite nunca frena la adquisición."""
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
            carpeta = self.dir_grabaciones / (datetime.now().strftime("%Y-%m-%d_%H%M%S") + (f"_{limpio}" if limpio else ""))
            self.t0_sesion = self.t_ahora()
            self.sesion = Sesion(carpeta, self.epoch(self.t0_sesion))
            self.parada_abierta = False
            self.aviso(f"Grabando en {carpeta.name}")
            return carpeta.name

    def detener_grabacion(self) -> str | None:
        with self.candado:
            if not self.sesion:
                return None
            nombre = self.sesion.carpeta.name
            self.sesion.cerrar()
            self.sesion = None
            self.aviso(f"Grabación guardada: {nombre}")
        self.vaciar_pendientes()
        return nombre

    # ---------------------------------------------------------------- estado para la web
    def estado(self) -> dict:
        with self.candado:
            sin_datos = time.monotonic() - self.mono_ultimo > 2.0
            return {
                "grabando": self.sesion is not None,
                "carpeta": self.sesion.carpeta.name if self.sesion else None,
                "t_grabacion_s": round(self.t_ahora() - self.t0_sesion, 1) if self.sesion else 0,
                "origen": self.origen, "id_nodo": self.id_nodo, "fs_hz": self.fs,
                "acelerometro_sin_datos": sin_datos, "muestras": self.n_acc,
                "gps": {"fix": self.fix, "lat": None if math.isnan(self.lat) else self.lat,
                        "lon": None if math.isnan(self.lon) else self.lon,
                        "precision_m": None if math.isnan(self.precision) else round(self.precision, 1),
                        "vel_kmh": round(self.vel_kmh, 1), "satelites": self.n_sat, "hora_de_gps": self.hora_de_gps},
                "ambiente": {k: v for k, v in self.amb.items() if not k.endswith("_t")},
                "distancia_mm": None if math.isnan(self.distancia_mm) else round(self.distancia_mm),
                "eventos": self.n_eventos_total, "eventos_sin_gps": self.n_eventos_sin_gps,
                "ultimos_eventos": self.eventos.ultimos(6), "etiquetas": self.etiquetas.ultimos(8),
                "n_etiquetas": len(self.etiquetas),
                "serie": self.serie.ultimos(600), "trayecto": self.trayecto.ultimos(1200)[::3],
                "sensores": {n: s.estado() for n, s in self.sensores.items()},
                "latencias": {k: w.resumen() for k, w in self.latencias.items() if w.n},
                "mensajes": list(self.mensajes),
            }
