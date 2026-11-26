"""Estado del modelo para mostrar en la app: modelos, cifras de inferencia y umbrales, con su rótulo.

Hoy todo sale de `config/simulacion.yaml` y es **SIMULADO**: los modelos se entrenaron con datos sintéticos y las
latencias se midieron en el PC. Cuando el API entregue el estado real, deja su JSON en `data/modelo/estado_api.json`
(fuera de Git) con el **mismo esquema** y la app lo prefiere sin cambiar nada más.

Esquema (versión 1) que devuelve `cargar()` y sirve `GET /api/modelo`:
    esquema: 1
    fuente: "simulacion" | "api"
    simulado: bool                  # True salvo que la fuente diga explícitamente false
    rotulo: "SIMULADO" | ...        # siempre "SIMULADO" si simulado es True
    actualizado: "AAAA-MM-DD"
    nota: str
    umbrales: {detector_en_vivo: {...}, detector_analisis: {...}, ventanas_modelo: {...}, umbral_confianza_modelo: ...}
    modelos: [{id, nombre, fecha, datos, archivos, ..., metricas_simuladas: {...}}]
    cifras_inferencia: {medidas_en, fecha, origen, etapas: [{etapa, media, desv, n}], proceso: {...}, pendiente}
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from viaviva import config

RUTA_SIMULACION = config.RAIZ / "config" / "simulacion.yaml"
RUTA_API = config.RAIZ / "data" / "modelo" / "estado_api.json"
CLAVES = ("umbrales", "modelos", "cifras_inferencia")


def _normalizar(d: dict, fuente: str) -> dict:
    """Rellena lo que falte y fuerza el rótulo: nada se muestra como real si la fuente no lo dice explícitamente."""
    simulado = d.get("simulado") is not False
    return {
        "esquema": d.get("esquema", 1),
        "fuente": d.get("fuente") or fuente,
        "simulado": simulado,
        "rotulo": "SIMULADO" if simulado else (d.get("rotulo") or ""),
        "actualizado": str(d.get("actualizado") or ""),
        "nota": d.get("nota") or "",
        "umbrales": d.get("umbrales") or {},
        "modelos": d.get("modelos") or [],
        "cifras_inferencia": d.get("cifras_inferencia") or {},
    }


def cargar(ruta_simulacion: Path = RUTA_SIMULACION, ruta_api: Path = RUTA_API) -> dict:
    """Prefiere el JSON del API si existe y se puede leer; si no, la simulación. Nunca lanza por un archivo del API roto:
    vuelve a la simulación y lo anota en `aviso`."""
    aviso = None
    if ruta_api.exists():
        try:
            d = json.loads(ruta_api.read_text(encoding="utf-8"))
            if isinstance(d, dict) and any(k in d for k in CLAVES):
                return _normalizar(d, "api")
            aviso = f"{ruta_api.name} no tiene el esquema esperado; se muestra la simulación"
        except (OSError, ValueError) as err:
            aviso = f"{ruta_api.name} no se pudo leer ({type(err).__name__}); se muestra la simulación"
    estado = _normalizar(yaml.safe_load(ruta_simulacion.read_text(encoding="utf-8")) or {}, "simulacion")
    if aviso:
        estado["aviso"] = aviso
    return estado
