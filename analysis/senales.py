"""Funciones de señales para VÍA VIVA: phyphox → filtro → espectro → ventanas → características → clasificador.

Lo usa el notebook 01_phyphox_clasificador.ipynb. Cuando lleguen los recorridos reales:

    from senales import procesar_carpeta
    resultado = procesar_carpeta("../data/raw/phyphox")

Formato esperado en data/raw/phyphox/ (una entrada por recorrido):
  * <recorrido>.csv          un CSV exportado de phyphox, o
  * <recorrido>/             la carpeta de un export de phyphox con varios CSV (Accelerometer.csv, Location.csv), o
  * <recorrido>.zip          el zip tal como lo exporta phyphox.
  * <recorrido>_etiquetas.csv (opcional) columnas t_s,clase  con clase en {hueco, resalto, impacto_fuerte}
    t_s = segundos desde el inicio de la grabación de phyphox (lo anota el copiloto).
Se aceptan separadores ',', ';' o tabulador y coma decimal.
Recomendado en phyphox: "Aceleración con g" + "Ubicación (GPS)" en un experimento propio, a la tasa más alta.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal, stats

CLASES = ["normal", "hueco", "resalto", "impacto_fuerte"]
G = 9.80665


# ============================================================================
# 1. Lectura de phyphox
# ============================================================================
def _leer_csv_flexible(fuente) -> pd.DataFrame:
    """Lee un CSV de phyphox con separador y decimal desconocidos."""
    texto = fuente.read() if hasattr(fuente, "read") else Path(fuente).read_bytes()
    if isinstance(texto, bytes):
        texto = texto.decode("utf-8-sig", errors="replace")
    primera = texto.splitlines()[0]
    sep = max([",", ";", "\t"], key=primera.count)
    decimal = "," if sep != "," and re.search(r"\d,\d", texto[:2000]) else "."
    return pd.read_csv(io.StringIO(texto), sep=sep, decimal=decimal)


def _buscar(cols, *patrones):
    for p in patrones:
        for c in cols:
            if re.search(p, c, re.IGNORECASE):
                return c
    return None


def _separar(df: pd.DataFrame):
    """De un DataFrame de phyphox saca acelerómetro, giroscopio y GPS (los que haya)."""
    cols = list(df.columns)
    t = _buscar(cols, r"^time", r"tiempo")
    # Android: "Acceleration x (m/s^2)"; iOS (phyphox 1.2, 7-nov): solo "X (m/s^2)" en Accelerometer.csv y
    # "X (rad/s)" en Gyroscope.csv. Por eso también se reconoce por las unidades.
    ax = _buscar(cols, r"acceleration x", r"aceleraci[oó]n x", r"\bax\b", r"^x \(m/s")
    ay = _buscar(cols, r"acceleration y", r"aceleraci[oó]n y", r"\bay\b", r"^y \(m/s")
    az = _buscar(cols, r"acceleration z", r"aceleraci[oó]n z", r"\baz\b", r"^z \(m/s")
    gx = _buscar(cols, r"gyroscope x", r"giroscopio x", r"\bgx\b", r"^x \(rad/s")
    gy = _buscar(cols, r"gyroscope y", r"giroscopio y", r"\bgy\b", r"^y \(rad/s")
    gz = _buscar(cols, r"gyroscope z", r"giroscopio z", r"\bgz\b", r"^z \(rad/s")
    lat = _buscar(cols, r"latitud")
    lon = _buscar(cols, r"longitud")
    vel = _buscar(cols, r"velocity", r"velocidad", r"speed")
    acc = giro = gps = None
    if t and ax and ay and az:
        acc = pd.DataFrame({"t": df[t], "ax": df[ax], "ay": df[ay], "az": df[az]}).dropna()
        acc.attrs["con_g"] = not re.search(r"linear|lineal|without|sin g", ax, re.IGNORECASE)
    if t and gx and gy and gz:
        giro = pd.DataFrame({"t": df[t], "gx": df[gx], "gy": df[gy], "gz": df[gz]}).dropna()   # rad/s
    if t and lat and lon:
        gps = pd.DataFrame({"t": df[t], "lat": df[lat], "lon": df[lon],
                            "vel": df[vel] if vel else np.nan}).dropna(subset=["lat", "lon"])
    return acc, giro, gps


def _tablas(ruta: Path) -> list[pd.DataFrame]:
    if ruta.is_dir():
        return [_leer_csv_flexible(p) for p in sorted(ruta.glob("*.csv"))]
    if ruta.suffix.lower() == ".zip":
        with zipfile.ZipFile(ruta) as z:
            return [_leer_csv_flexible(z.open(n)) for n in z.namelist()
                    if n.lower().endswith(".csv") and not n.startswith("meta/")]
    return [_leer_csv_flexible(ruta)]


def cargar_phyphox_completo(ruta) -> dict:
    """{'acc', 'giro', 'gps'}: acelerómetro (t, ax, ay, az en m/s²), giroscopio (t, gx, gy, gz en rad/s) y GPS
    (t, lat, lon, vel en m/s). giro y gps pueden ser None si el experimento no los tenía."""
    ruta = Path(ruta)
    salida = {"acc": None, "giro": None, "gps": None}
    for df in _tablas(ruta):
        for clave, valor in zip(("acc", "giro", "gps"), _separar(df)):
            if salida[clave] is None and valor is not None:
                salida[clave] = valor.reset_index(drop=True)
    if salida["acc"] is None:
        raise ValueError(f"{ruta}: no se encontraron columnas de aceleración x/y/z")
    return salida


def cargar_phyphox(ruta) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Devuelve (acelerómetro, gps). acelerómetro: t [s], ax, ay, az [m/s²]; gps: t, lat, lon, vel [m/s]."""
    d = cargar_phyphox_completo(ruta)
    return d["acc"], d["gps"]


# ============================================================================
# 2. Preprocesamiento: remuestreo, gravedad, eje vertical, filtro
# ============================================================================
def tasa_nativa(t: np.ndarray) -> float:
    """fs del teléfono a partir de la mediana de los intervalos (phyphox no muestrea parejo)."""
    return float(1.0 / np.median(np.diff(t)))


def remuestrear(acc: pd.DataFrame, fs: float) -> pd.DataFrame:
    t = acc["t"].to_numpy()
    tu = np.arange(t[0], t[-1], 1.0 / fs)
    return pd.DataFrame({"t": tu, **{c: np.interp(tu, t, acc[c].to_numpy()) for c in ("ax", "ay", "az")}})


def pasa_bajos(x: np.ndarray, fs: float, fc: float, orden: int = 4) -> np.ndarray:
    """Butterworth de fase cero (filtfilt): sin retraso, válido fuera de línea."""
    sos = signal.butter(orden, fc, btype="low", fs=fs, output="sos")
    return signal.sosfiltfilt(sos, x, axis=0)


def eje_vertical(acc_u: pd.DataFrame, fs: float, con_g: bool = True) -> np.ndarray:
    """Aceleración dinámica sobre el eje de la gravedad (m/s²), sin importar la orientación del teléfono.

    La gravedad se estima con un pasa-bajos de 0,3 Hz y se proyecta la parte dinámica sobre ella.
    Si phyphox entregó aceleración SIN g, no hay referencia: se usa la magnitud (aproximación).
    """
    a = acc_u[["ax", "ay", "az"]].to_numpy()
    if not con_g:
        return np.linalg.norm(a, axis=1) - np.linalg.norm(a, axis=1).mean()
    g_est = pasa_bajos(a, fs, 0.3, orden=2)
    unit = g_est / np.linalg.norm(g_est, axis=1, keepdims=True)
    return np.einsum("ij,ij->i", a - g_est, unit)


# ============================================================================
# 3. Espectro y elección de fs (Nyquist con el 95 % de la energía)
# ============================================================================
@dataclass
class Espectro:
    f: np.ndarray
    psd: np.ndarray
    f_energia: float          # frecuencia bajo la cual queda `fraccion` de la energía
    fraccion: float
    fs_minima: float          # 2 × f_energia (Nyquist)
    fs_recomendada: float     # con margen de 2,5 × f_energia para el filtro antialias


def espectro(x: np.ndarray, fs: float, fraccion: float = 0.95) -> Espectro:
    f, psd = signal.welch(x, fs=fs, nperseg=min(len(x), int(4 * fs)))
    acumulada = np.cumsum(psd) / np.sum(psd)
    f_e = float(f[np.searchsorted(acumulada, fraccion)])
    return Espectro(f, psd, f_e, fraccion, 2 * f_e, 2.5 * f_e)


# ============================================================================
# 4. Ventanas por energía / jerk
# ============================================================================
def detectar_ventanas(a: np.ndarray, fs: float, dur_s: float = 1.0, k: float = 4.0,
                      refractario_s: float = 1.0) -> list[int]:
    """Índices centrales de eventos: donde la energía de corto plazo (0,25 s) o el jerk superan k × su mediana."""
    n = max(1, int(0.25 * fs))
    energia = np.convolve(a ** 2, np.ones(n) / n, mode="same")
    jerk = np.abs(np.gradient(a) * fs)
    umbral_e = k * np.median(energia) + 1e-12
    umbral_j = k * np.median(jerk) + 1e-12
    candidatos = np.flatnonzero((energia > umbral_e) | (jerk > 2 * umbral_j))
    centros, ultimo = [], -np.inf
    medio = int(dur_s * fs / 2)
    for i in candidatos:
        if i - ultimo < refractario_s * fs:
            continue
        lo, hi = max(0, i - medio), min(len(a), i + medio)
        c = lo + int(np.argmax(np.abs(a[lo:hi])))      # se centra en el pico
        if medio <= c < len(a) - medio:
            centros.append(c)
            ultimo = c
    return centros


def ventanas_normales(a: np.ndarray, fs: float, centros_evento: list[int], cantidad: int,
                      dur_s: float = 1.0, semilla: int = 0) -> list[int]:
    """Centros al azar lejos (≥2 s) de cualquier evento: ejemplos de la clase 'normal'."""
    rng = np.random.default_rng(semilla)
    medio = int(dur_s * fs / 2)
    lejos = int(2 * fs)
    eventos = np.array(centros_evento)
    elegidos, intentos = [], 0
    while len(elegidos) < cantidad and intentos < 50 * cantidad:
        c = int(rng.integers(medio, len(a) - medio))
        intentos += 1
        if eventos.size and np.min(np.abs(eventos - c)) < lejos:
            continue
        if elegidos and np.min(np.abs(np.array(elegidos) - c)) < 2 * medio:
            continue
        elegidos.append(c)
    return elegidos


# ============================================================================
# 5. Características
# ============================================================================
BANDAS_HZ = [(0.5, 5), (5, 15), (15, 30), (30, 80)]


def caracteristicas(v: np.ndarray, fs: float, velocidad: float = np.nan) -> dict:
    """Pico, RMS, curtosis, factor de cresta, jerk y energía por banda de una ventana (m/s²).

    Las de amplitud se normalizan además por la velocidad (m/s) cuando se conoce:
    el mismo hueco golpea más fuerte a 40 km/h que a 20 km/h.
    """
    pico = float(np.max(np.abs(v)))
    rms = float(np.sqrt(np.mean(v ** 2)))
    f, psd = signal.periodogram(v - v.mean(), fs=fs)
    total = np.trapezoid(psd, f) + 1e-12
    d = {
        "pico": pico,
        "rms": rms,
        "curtosis": float(stats.kurtosis(v, fisher=False)),
        "factor_cresta": pico / (rms + 1e-12),
        "jerk_max": float(np.max(np.abs(np.diff(v))) * fs),
        "signo_pico": float(np.sign(v[np.argmax(np.abs(v))])),
        "asimetria": float(stats.skew(v)),
        "velocidad": velocidad,
    }
    for lo, hi in BANDAS_HZ:
        m = (f >= lo) & (f < min(hi, fs / 2))
        d[f"energia_{lo:g}_{hi:g}hz"] = float(np.trapezoid(psd[m], f[m]) / total) if m.sum() > 1 else 0.0
    v_ok = velocidad if velocidad and velocidad > 1.0 else np.nan
    d["pico_por_vel"] = pico / v_ok
    d["rms_por_vel"] = rms / v_ok
    return d


# ============================================================================
# 6. Un recorrido completo → tabla de ventanas con características y etiqueta
# ============================================================================
@dataclass
class Recorrido:
    nombre: str
    fs: float
    t: np.ndarray
    a_vert: np.ndarray
    fs_nativa: float
    espectro: Espectro
    ventanas: pd.DataFrame = field(default_factory=pd.DataFrame)
    gps: pd.DataFrame | None = None
    a_sin_filtro: np.ndarray | None = None


def _etiquetas_de(ruta: Path) -> pd.DataFrame | None:
    base = ruta.with_suffix("") if ruta.suffix else ruta
    p = base.parent / f"{base.name}_etiquetas.csv"
    if p.exists():
        df = _leer_csv_flexible(p)
        df.columns = [c.strip().lower() for c in df.columns]
        return df[["t_s", "clase"]]
    return None


def procesar_recorrido(acc: pd.DataFrame, gps: pd.DataFrame | None, nombre: str,
                       etiquetas: pd.DataFrame | None = None, fs: float | None = None,
                       tolerancia_s: float = 1.0) -> Recorrido:
    fs_nat = tasa_nativa(acc["t"].to_numpy())
    fs = fs or min(200.0, round(fs_nat))
    acc_u = remuestrear(acc, fs)
    a_sin_filtro = eje_vertical(acc_u, fs, acc.attrs.get("con_g", True))
    esp = espectro(a_sin_filtro, fs)             # espectro ANTES del filtro: es lo que define fs
    a = pasa_bajos(a_sin_filtro, fs, min(80.0, 0.4 * fs))   # antialias / ruido
    t = acc_u["t"].to_numpy()

    vel = np.full_like(t, np.nan)
    if gps is not None and len(gps) > 1 and gps["vel"].notna().any():
        g = gps.dropna(subset=["vel"])
        vel = np.interp(t, g["t"].to_numpy(), g["vel"].to_numpy())

    centros = detectar_ventanas(a, fs)
    normales = ventanas_normales(a, fs, centros, cantidad=max(len(centros), 5))
    medio = int(0.5 * fs)
    filas = []
    for c, origen in [(c, "detectada") for c in centros] + [(c, "normal") for c in normales]:
        d = caracteristicas(a[c - medio:c + medio], fs, float(vel[c]))
        d.update({"recorrido": nombre, "t_s": float(t[c]), "origen": origen})
        if gps is not None and len(gps) > 1:
            d["lat"] = float(np.interp(t[c], gps["t"], gps["lat"]))
            d["lon"] = float(np.interp(t[c], gps["t"], gps["lon"]))
        filas.append(d)
    ventanas = pd.DataFrame(filas)

    # Etiquetas: cada etiqueta del copiloto se asigna a la ventana detectada más cercana (≤ tolerancia).
    ventanas["clase"] = np.where(ventanas["origen"] == "normal", "normal", None)
    if etiquetas is not None and not ventanas.empty:
        det = ventanas.index[ventanas["origen"] == "detectada"]
        for _, e in etiquetas.iterrows():
            if len(det) == 0:
                break
            dist = (ventanas.loc[det, "t_s"] - float(e["t_s"])).abs()
            if dist.min() <= tolerancia_s:
                ventanas.loc[dist.idxmin(), "clase"] = str(e["clase"]).strip().lower()
        # Ventanas detectadas sin etiqueta: falsas alarmas del detector → clase 'normal'
        ventanas.loc[(ventanas["origen"] == "detectada") & ventanas["clase"].isna(), "clase"] = "normal"
    return Recorrido(nombre, fs, t, a, fs_nat, esp, ventanas, gps, a_sin_filtro)


# ============================================================================
# 7. Clasificador con validación leave-one-drive-out
# ============================================================================
def columnas_caracteristicas(df: pd.DataFrame) -> list[str]:
    fuera = {"recorrido", "t_s", "origen", "clase", "lat", "lon"}
    return [c for c in df.columns if c not in fuera]


def entrenar_lodo(ventanas: pd.DataFrame, semilla: int = 0) -> dict:
    """Bosque aleatorio y árbol de decisión (exportable a C), validados dejando un recorrido fuera."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import classification_report, confusion_matrix, f1_score
    from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.tree import DecisionTreeClassifier

    datos = ventanas.dropna(subset=["clase"])
    grupos = datos["recorrido"]
    if grupos.nunique() < 2:
        raise ValueError("Leave-one-drive-out necesita al menos 2 recorridos etiquetados.")
    X = datos[columnas_caracteristicas(datos)].replace([np.inf, -np.inf], np.nan)
    y = datos["clase"]
    modelos = {
        "bosque": make_pipeline(SimpleImputer(strategy="median"),
                                RandomForestClassifier(n_estimators=200, class_weight="balanced",
                                                       random_state=semilla)),
        "arbol": make_pipeline(SimpleImputer(strategy="median"),
                               DecisionTreeClassifier(max_depth=4, class_weight="balanced",
                                                      random_state=semilla)),
    }
    etiquetas = [c for c in CLASES if c in set(y)]
    resultados = {}
    for nombre, modelo in modelos.items():
        pred = cross_val_predict(modelo, X, y, groups=grupos, cv=LeaveOneGroupOut())
        resultados[nombre] = {
            "f1_macro": f1_score(y, pred, average="macro"),
            "f1_hueco": f1_score(y, pred, labels=["hueco"], average="macro") if "hueco" in etiquetas else np.nan,
            "reporte": classification_report(y, pred, labels=etiquetas, zero_division=0),
            "confusion": pd.DataFrame(confusion_matrix(y, pred, labels=etiquetas), index=etiquetas, columns=etiquetas),
            "modelo_final": modelo.fit(X, y),
        }
    resultados["columnas"] = list(X.columns)
    resultados["n_ventanas"] = len(datos)
    resultados["n_recorridos"] = int(grupos.nunique())
    return resultados


# ============================================================================
# 8. Punto de entrada para los datos reales
# ============================================================================
def procesar_carpeta(carpeta="../data/raw/phyphox", fs: float | None = None) -> dict:
    """Procesa todos los recorridos de phyphox de la carpeta y, si hay etiquetas de ≥2 recorridos, entrena."""
    carpeta = Path(carpeta)
    entradas = [p for p in sorted(carpeta.glob("*"))
                if not p.name.endswith("_etiquetas.csv") and (p.is_dir() or p.suffix.lower() in (".csv", ".zip"))]
    if not entradas:
        raise FileNotFoundError(f"No hay recorridos en {carpeta.resolve()}")
    recorridos = []
    for p in entradas:
        acc, gps = cargar_phyphox(p)
        recorridos.append(procesar_recorrido(acc, gps, p.stem, _etiquetas_de(p), fs=fs))
    ventanas = pd.concat([r.ventanas for r in recorridos], ignore_index=True)
    salida = {"recorridos": recorridos, "ventanas": ventanas, "modelos": None}
    con_etiqueta = {r.nombre for r in recorridos if _etiquetas_de(carpeta / r.nombre) is not None
                    or _etiquetas_de(carpeta / f"{r.nombre}.csv") is not None}
    if len(con_etiqueta) >= 2:
        salida["modelos"] = entrenar_lodo(ventanas[ventanas["recorrido"].isin(con_etiqueta)])
    return salida


# ============================================================================
# 9. Datos SINTÉTICOS (solo para probar que el código corre; NO son resultados)
# ============================================================================
def recorrido_sintetico(nombre: str, duracion_s: float = 180, fs_tel: float = 400, semilla: int = 0):
    """Genera un recorrido falso con huecos, resaltos e impactos para probar el flujo completo.

    Devuelve (acc, gps, etiquetas) con el mismo formato que cargar_phyphox + etiquetas.
    Los números que salgan de aquí NO describen las vías de Tunja.
    """
    rng = np.random.default_rng(semilla)
    t = np.arange(0, duracion_s, 1 / fs_tel)
    t = t + rng.normal(0, 0.1 / fs_tel, t.size)          # muestreo irregular como un teléfono
    t.sort()
    vel = np.clip(8 + 2 * np.sin(2 * np.pi * t / 60) + rng.normal(0, 0.2, t.size), 3, 12)  # m/s
    # Vibración de la vía: ruido filtrado + modo de la carrocería (~1,5 Hz) + rueda (~12 Hz)
    ruido = signal.sosfilt(signal.butter(2, 25, fs=fs_tel, output="sos"), rng.normal(0, 1.2, t.size))
    vert = ruido + 0.3 * np.sin(2 * np.pi * 1.5 * t) + 0.2 * np.sin(2 * np.pi * 12 * t + 1)
    etiquetas = []
    for te in np.arange(8, duracion_s - 5, rng.uniform(6, 10)):
        clase = rng.choice(["hueco", "resalto", "impacto_fuerte"], p=[0.5, 0.3, 0.2])
        tau = t - te
        m = (tau >= 0) & (tau < 1.5)
        if clase == "hueco":       # caída y rebote amortiguado
            vert[m] += -6 * np.exp(-tau[m] / 0.08) * np.cos(2 * np.pi * 11 * tau[m])
        elif clase == "resalto":   # subida lenta y bajada
            vert[m] += 4 * np.sin(2 * np.pi * 1.2 * tau[m]) * np.exp(-tau[m] / 0.4)
        else:                      # golpe seco de alta frecuencia
            vert[m] += 18 * np.exp(-tau[m] / 0.02) * np.sin(2 * np.pi * 35 * tau[m])
        etiquetas.append((te + rng.normal(0, 0.15), clase))   # el copiloto no es exacto
    # Teléfono inclinado: la gravedad no cae sobre z
    ang = np.deg2rad(rng.uniform(10, 40))
    acc = pd.DataFrame({"t": t, "ax": 0.3 * rng.normal(0, 1, t.size),
                        "ay": (G + vert) * np.sin(ang), "az": (G + vert) * np.cos(ang)})
    acc.attrs["con_g"] = True
    tg = np.arange(0, duracion_s, 1.0)                    # GPS a 1 Hz
    vg = np.interp(tg, t, vel)
    dist = np.cumsum(vg)
    gps = pd.DataFrame({"t": tg, "lat": 5.5353 + dist / 111_320, "lon": np.full(tg.size, -73.3678), "vel": vg})
    return acc, gps, pd.DataFrame(etiquetas, columns=["t_s", "clase"])
