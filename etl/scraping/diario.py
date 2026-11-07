"""Scraping diario (R5): lluvia IDEAM incremental + noticias, con log por corrida y chequeo de frescura.

Cada corrida:
  1. IDEAM: últimos --dias (3 por defecto) de las estaciones ≤ 15 km; sin duplicados (hash_contenido).
  2. Noticias (RSS/HTML permitidos por robots.txt).
  3. Frescura: si el último ts_dato de lluvia tiene más de --max-dias días, avisa "DESACTUALIZADO".
  4. Agrega una línea a data/logs/scraping_diario.jsonl (fecha, filas nuevas y actualizadas, errores, frescura) y
     termina con código 1 si hubo error o los datos están viejos (el Programador de tareas lo muestra como fallo).

Uso (desde via-viva/):
  etl\\.venv\\Scripts\\python -m etl.scraping.diario
  etl\\.venv\\Scripts\\python -m etl.scraping.diario --resumen        (tabla de las últimas corridas: evidencia para R5)
Programarlo todos los días: herramientas\\programar_scraping.ps1 (Programador de tareas de Windows, schtasks).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import date, datetime, timezone

from etl.config import DATA
from etl.db import conectar

LOG = DATA / "logs" / "scraping_diario.jsonl"


def frescura(con, max_dias: int) -> dict:
    """Edad (días) del dato más reciente de lluvia y de noticias."""
    lluvia = con.execute("SELECT MAX(substr(ts_dato, 1, 10)) FROM fuentes_externas "
                         "WHERE variable = 'precipitacion_diaria_mm'").fetchone()[0]
    noticia = con.execute("SELECT MAX(substr(ts_captura, 1, 10)) FROM fuentes_externas WHERE tipo != 'clima'"
                          ).fetchone()[0]
    edad = (date.today() - date.fromisoformat(lluvia)).days if lluvia else None
    return {"ultimo_ts_dato_lluvia": lluvia, "edad_dias_lluvia": edad, "ultima_captura_noticias": noticia,
            "desactualizado": edad is None or edad > max_dias, "max_dias": max_dias}


def correr(dias: int, max_dias: int) -> dict:
    t0 = time.monotonic()
    registro = {"inicio": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"), "dias": dias,
                "ideam": None, "noticias": None, "errores": []}
    # Si el PC estuvo apagado varios días, la ventana se amplía hasta el último dato guardado (no quedan huecos)
    con = conectar()
    previa = frescura(con, max_dias)["edad_dias_lluvia"]
    con.close()
    if previa is not None and previa + 1 > dias:
        registro["dias"] = dias = min(previa + 1, 60)
    try:
        from etl.scraping import clima_ideam
        registro["ideam"] = clima_ideam.ejecutar(dias)
    except BaseException as e:                       # SystemExit (robots.txt) también queda en el log
        registro["errores"].append({"paso": "ideam", "error": f"{type(e).__name__}: {e}"})
        traceback.print_exc()
    try:
        from etl.scraping import noticias
        from etl.scraping.comun import ClienteRespetuoso
        registro["noticias"] = noticias.ejecutar(ClienteRespetuoso())
    except BaseException as e:
        registro["errores"].append({"paso": "noticias", "error": f"{type(e).__name__}: {e}"})
        traceback.print_exc()
    con = conectar()
    registro["frescura"] = frescura(con, max_dias)
    con.close()
    registro["duracion_s"] = round(time.monotonic() - t0, 1)
    registro["ok"] = not registro["errores"] and not registro["frescura"]["desactualizado"]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return registro


def resumen(n: int = 15) -> str:
    if not LOG.exists():
        return "Todavía no hay corridas registradas."
    filas = [json.loads(l) for l in LOG.read_text(encoding="utf-8").splitlines() if l.strip()][-n:]
    l = ["| Inicio | IDEAM nuevos / act. | Noticias nuevas | Último dato de lluvia (edad) | Errores | OK |",
         "|---|---|---|---|---|---|"]
    for r in filas:
        i, no, fr = r.get("ideam") or {}, r.get("noticias") or {}, r["frescura"]
        l.append(f"| {r['inicio']} | {i.get('nuevos', '–')} / {i.get('actualizados', '–')} | {no.get('nuevas', '–')} | "
                 f"{fr['ultimo_ts_dato_lluvia']} ({fr['edad_dias_lluvia']} d) | {len(r['errores'])} | "
                 f"{'sí' if r['ok'] else 'NO'} |")
    return "\n".join(l)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dias", type=int, default=3, help="días hacia atrás de IDEAM en cada corrida")
    ap.add_argument("--max-dias", type=int, default=3, help="frescura: avisar si el último dato es más viejo")
    ap.add_argument("--resumen", action="store_true")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    if a.resumen:
        print(resumen())
        return
    r = correr(a.dias, a.max_dias)
    fr = r["frescura"]
    print(f"\nCorrida {'OK' if r['ok'] else 'CON PROBLEMAS'} en {r['duracion_s']} s · IDEAM {r['ideam']} · "
          f"noticias {r['noticias']} · último dato de lluvia {fr['ultimo_ts_dato_lluvia']} "
          f"({fr['edad_dias_lluvia']} días){' — DESACTUALIZADO' if fr['desactualizado'] else ''} · log: {LOG}")
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
