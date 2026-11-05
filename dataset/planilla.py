"""Planilla de campo del equipo (Google Sheets → Archivo → Descargar → CSV) unida a las fotos.

Columnas de la planilla (los nombres se reconocen sin importar tildes, mayúsculas ni signos):
  N.º, Fecha, Hora, Clase, Severidad, Tipo de vía (= SUPERFICIE: asfalto/concreto/adoquín/destapada), ¿Mojado?, Luz,
  Clima, Barrio/calle, Fotógrafo, N.º fotos, Notas
Los CSV van en data/raw/planilla/ (puede haber varios: uno por día o la planilla completa).

Unión con las fotos: cada fila se asigna a las fotos tomadas a ± VENTANA_MIN minutos de su hora (del mismo fotógrafo
si el nombre coincide con el autor de la carpeta) y, por GPS, a todas las fotos del mismo SITIO de esas fotos.
Solo llena columnas que están VACÍAS (lo que se marcó en el etiquetador manda).
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

from dataset.comun import CLASES, LUCES, SEVERIDADES, SUPERFICIES

VENTANA_MIN = 5

# encabezado normalizado → nombre interno
ENCABEZADOS = {"no": "n", "n": "n", "numero": "n", "fecha": "fecha", "hora": "hora", "clase": "clase",
               "severidad": "severidad", "tipodevia": "superficie", "superficie": "superficie", "mojado": "mojado",
               "luz": "luz", "clima": "clima", "barriocalle": "barrio_calle", "barrio": "barrio_calle",
               "fotografo": "fotografo", "nofotos": "n_fotos", "nfotos": "n_fotos", "notas": "notas"}

# texto libre → clase del dataset
SINONIMOS_CLASE = {"hueco": "hueco", "bache": "hueco", "resalto": "resalto", "reductor": "resalto",
                   "policiaacostado": "resalto", "grieta": "grieta", "fisura": "grieta", "parche": "parche",
                   "tapa": "tapa", "alcantarilla": "tapa", "sumidero": "tapa", "rejilla": "tapa",
                   "obstaculo": "obstaculo", "escombro": "obstaculo", "lineadecarril": "linea_carril",
                   "linea": "linea_carril", "lineacarril": "linea_carril", "pasopeatonal": "paso_peatonal",
                   "cebra": "paso_peatonal", "viabuena": "via_buena", "buena": "via_buena", "sindano": "via_buena"}
SINONIMOS_SUPERFICIE = {"asfalto": "asfalto", "pavimento": "asfalto", "concreto": "concreto", "rigido": "concreto",
                        "adoquin": "adoquin", "adoquinado": "adoquin", "destapada": "destapada", "tierra": "destapada",
                        "afirmado": "destapada", "sinpavimentar": "destapada"}
SINONIMOS_LUZ = {"sol": "sol", "soleado": "sol", "sombra": "sombra", "nublado": "nublado", "noche": "noche"}


def clave(texto) -> str:
    """'¿Mojado?' → 'mojado'; 'Línea de carril' → 'lineadecarril'."""
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", t.replace("º", "o"))


def _mapear(valor, sinonimos: dict, validos: list) -> str:
    k = clave(valor)
    if not k:
        return ""
    if k in sinonimos:
        return sinonimos[k]
    return next((v for s, v in sinonimos.items() if s in k), k if k in validos else "")


def _fecha_hora(fecha, hora) -> pd.Timestamp:
    f = str(fecha).strip()
    h = str(hora).strip().lower().replace("p. m.", "pm").replace("a. m.", "am").replace("p.m.", "pm").replace("a.m.", "am")
    iso = bool(re.match(r"\d{4}-\d{1,2}-\d{1,2}", f))
    return pd.to_datetime(f"{f} {h}", dayfirst=not iso, errors="coerce")


def leer(carpeta: Path) -> tuple[pd.DataFrame, list[str]]:
    """Todas las planillas de la carpeta, normalizadas. Devuelve (tabla, avisos)."""
    avisos, partes = [], []
    for p in sorted(carpeta.glob("*.csv")) if carpeta.exists() else []:
        d = pd.read_csv(p, dtype=str, keep_default_na=False, sep=None, engine="python", encoding="utf-8-sig")
        nombres = {c: ENCABEZADOS.get(clave(c)) for c in d.columns}
        faltan = {"fecha", "hora", "clase"} - set(nombres.values())
        if faltan:
            avisos.append(f"planilla `{p.name}`: no encontré las columnas {sorted(faltan)}; vi {list(d.columns)}")
            continue
        d = d.rename(columns={c: n for c, n in nombres.items() if n}).loc[:, [n for n in nombres.values() if n]]
        d["archivo_planilla"] = p.name
        partes.append(d)
    if not partes:
        return pd.DataFrame(), avisos
    t = pd.concat(partes, ignore_index=True)
    for c in ["n", "severidad", "superficie", "mojado", "luz", "clima", "barrio_calle", "fotografo", "notas"]:
        if c not in t:
            t[c] = ""
    t["t"] = [_fecha_hora(f, h) for f, h in zip(t["fecha"], t["hora"])]
    malas = t["t"].isna().sum()
    if malas:
        avisos.append(f"planilla: {malas} filas con fecha u hora que no se entienden (se ignoran)")
    t = t.dropna(subset=["t"])
    t["clase_n"] = [_mapear(v, SINONIMOS_CLASE, CLASES) for v in t["clase"]]
    t["severidad_n"] = [v if v in SEVERIDADES else "" for v in (clave(x) for x in t["severidad"])]
    t["superficie_n"] = [_mapear(v, SINONIMOS_SUPERFICIE, SUPERFICIES) for v in t["superficie"]]
    t["mojado_n"] = ["si" if clave(v) in ("si", "s", "yes", "x") else "no" if clave(v) in ("no", "n") else ""
                     for v in t["mojado"]]
    t["luz_n"] = [_mapear(v, SINONIMOS_LUZ, LUCES) for v in t["luz"]]
    sin_clase = (t["clase_n"] == "") & (t["clase"] != "")
    if sin_clase.any():
        avisos.append(f"planilla: clases que no reconozco: {sorted(set(t.loc[sin_clase, 'clase']))}")
    return t.reset_index(drop=True), avisos


def unir(meta: pd.DataFrame, plan: pd.DataFrame, sitio: pd.Series) -> tuple[pd.DataFrame, dict]:
    """Llena clase, severidad, superficie, mojado, luz y notas desde la planilla (solo celdas vacías)."""
    est = {"filas": len(plan), "filas_unidas": 0, "fotos_llenadas": 0}
    if plan.empty or meta.empty:
        return meta, est
    t_foto = pd.to_datetime(meta["fecha"] + " " + meta["hora"], errors="coerce")
    asignada: dict[int, tuple[float, int]] = {}            # índice de foto → (minutos de diferencia, fila)
    for j, f in plan.iterrows():
        dif = (t_foto - f["t"]).abs().dt.total_seconds() / 60
        cerca = dif <= VENTANA_MIN
        quien = clave(f["fotografo"])
        if quien:
            mismo = meta["autor"].map(lambda a: bool(clave(a)) and (clave(a) in quien or quien in clave(a)))
            if (cerca & mismo).any():
                cerca &= mismo
        if not cerca.any():
            continue
        est["filas_unidas"] += 1
        sitios_fila = set(sitio[cerca[cerca].index])
        for k in meta.index[sitio.isin(sitios_fila)]:   # todas las fotos del mismo sitio
            d = dif[k] if pd.notna(dif[k]) else 1e9
            if k not in asignada or d < asignada[k][0]:
                asignada[k] = (d, j)
    meta = meta.copy()
    for k, (_, j) in asignada.items():
        f = plan.loc[j]
        lleno = False
        for col, val in [("clase", f["clase_n"]), ("severidad", f["severidad_n"]), ("superficie", f["superficie_n"]),
                         ("superficie_mojada", f["mojado_n"]), ("luz", f["luz_n"])]:
            if val and not meta.at[k, col]:
                meta.at[k, col] = val
                lleno = True
        extra = "; ".join(x for x in [f"planilla {f['archivo_planilla']} n.º {f['n']}".strip(),
                                      f"clima={f['clima']}" if f["clima"] else "",
                                      f"lugar={f['barrio_calle']}" if f["barrio_calle"] else "",
                                      f["notas"]] if x)
        if extra and "planilla " not in meta.at[k, "notas"]:
            meta.at[k, "notas"] = (meta.at[k, "notas"] + " | " + extra).strip(" |")
        if meta.at[k, "clase"] not in ("", None) and meta.at[k, "clase"] not in CLASES_DANO_SET:
            meta.at[k, "severidad"] = ""
        est["fotos_llenadas"] += lleno
    return meta, est


from dataset.comun import CLASES_DANO as CLASES_DANO_SET  # noqa: E402  (al final para no tapar el docstring)
