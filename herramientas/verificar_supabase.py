"""Verifica el esquema y la RLS de Supabase de VÍA VIVA: en el archivo SQL (sin red) y contra el proyecto real.

    python herramientas/verificar_supabase.py --solo-sql      (sin red: revisa viaviva/supabase_esquema.sql)
    python herramientas/verificar_supabase.py                 (con el .env de la raíz: SUPABASE_URL,
                                                               SUPABASE_CLAVE_PUBLICA y SUPABASE_CLAVE)

Comprueba lo que promete el diseño (docs/SEGURIDAD.md, docs/NUBE.md):
  * la clave pública (anon) SIN sesión no lee ninguna fila de las tablas sincronizadas ni puede escribir;
  * la clave secreta (service_role, solo en el .env de la Pi o del PC que sincroniza) escribe, lee y borra.
Contra el proyecto real escribe UNA fila de prueba (`id_origen` = `VERIFICACION|…`, origen `verificacion`) en
eventos_publicos y la borra al final. Nunca imprime las claves. Sale con 0 si todo está OK.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ESQUEMA = RAIZ / "viaviva" / "supabase_esquema.sql"
TABLAS = ("perfiles", "eventos_publicos", "huecos_publicos", "riesgo_publico", "cambios_remotos")
SINCRONIZADAS = ("eventos_publicos", "huecos_publicos", "riesgo_publico", "cambios_remotos")


# ------------------------------------------------------------------ revisión del archivo SQL (sin red)
def revisar_sql(texto: str) -> list[tuple[bool, str]]:
    sql = re.sub(r"--[^\n]*", "", texto).lower()
    r = []
    for t in TABLAS:
        r.append((f"create table if not exists {t}" in sql, f"tabla {t} definida"))
        r.append((f"alter table {t} enable row level security" in sql, f"RLS activada en {t}"))
    r.append((" to anon" not in sql and "to public" not in sql, "ninguna política para anon/public"))
    r.append((not re.search(r"using\s*\(\s*true\s*\)", sql), "ninguna política abierta (using (true))"))
    r.append((not re.search(r"for\s+(update|delete|all)\b", sql), "nadie con sesión actualiza ni borra (solo service_role)"))
    r.append(("security_invoker = true" in sql, "la vista riesgo_ultimo respeta la RLS (security_invoker)"))
    return r


# ------------------------------------------------------------------ pruebas contra el proyecto
def _pedir(url: str, clave: str, metodo: str, ruta: str, datos=None, prefer: str = "return=representation"):
    req = urllib.request.Request(f"{url}/rest/v1/{ruta}", method=metodo,
                                 data=None if datos is None else json.dumps(datos).encode(),
                                 headers={"apikey": clave, "Authorization": f"Bearer {clave}",
                                          "Content-Type": "application/json", "Prefer": prefer})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            cuerpo = resp.read()
            return resp.status, (json.loads(cuerpo) if cuerpo else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def revisar_proyecto(url: str, publica: str, secreta: str) -> list[tuple[bool, str]]:
    url = url.rstrip("/")
    r = []
    marca = f"VERIFICACION|{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}"
    fila = {"id_origen": marca, "ts_utc": datetime.now(UTC).isoformat(), "lat": 5.535, "lon": -73.367,
            "clase": "hueco", "origen": "verificacion"}
    st, _ = _pedir(url, secreta, "POST", "eventos_publicos", [fila])
    r.append((st in (200, 201), f"service_role escribe en eventos_publicos (HTTP {st})"))
    st, filas = _pedir(url, secreta, "GET", f"eventos_publicos?id_origen=eq.{marca}&select=id_origen")
    r.append((st == 200 and bool(filas), f"service_role lee la fila de prueba (HTTP {st})"))
    for t in SINCRONIZADAS:
        st, filas = _pedir(url, publica, "GET", f"{t}?select=*&limit=1")
        r.append((st in (401, 403) or (st == 200 and filas == []),
                  f"anon sin sesión NO lee {t} (HTTP {st}, {len(filas or [])} filas)"))
    st, _ = _pedir(url, publica, "POST", "eventos_publicos", [dict(fila, id_origen=marca + "|anon")])
    r.append((st in (401, 403), f"anon sin sesión NO escribe en eventos_publicos (HTTP {st})"))
    st, _ = _pedir(url, publica, "POST", "cambios_remotos",
                   [{"id_origen": marca, "instancia": "verificacion", "id_local": 0, "estado": "reparado"}])
    r.append((st in (401, 403, 409), f"anon sin sesión NO pide cambios (HTTP {st})"))
    st, filas = _pedir(url, publica, "DELETE", f"eventos_publicos?id_origen=eq.{marca}")
    r.append((st in (401, 403) or not filas, f"anon sin sesión NO borra (HTTP {st})"))
    st, _ = _pedir(url, secreta, "DELETE", f"eventos_publicos?id_origen=like.VERIFICACION*", prefer="return=minimal")
    r.append((st in (200, 204), f"service_role borra las filas de prueba (HTTP {st})"))
    return r


def _leer_env(ruta: Path) -> dict:
    d = {}
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                k, v = linea.split("=", 1)
                d[k.strip()] = v.split(" #")[0].strip().strip('"').strip("'")
    return d


def _imprimir(titulo: str, r: list[tuple[bool, str]]) -> bool:
    print(f"== {titulo}")
    for ok, texto in r:
        print(f"  [{' OK  ' if ok else 'FALLA'}] {texto}")
    return all(ok for ok, _ in r)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--solo-sql", action="store_true", help="solo revisa viaviva/supabase_esquema.sql (sin red)")
    ap.add_argument("--env", default=str(RAIZ / ".env"), help="archivo .env (por defecto, el de la raíz)")
    a = ap.parse_args(argv)
    bien = _imprimir("Archivo SQL", revisar_sql(ESQUEMA.read_text(encoding="utf-8")))
    if a.solo_sql:
        return 0 if bien else 1
    env = {**_leer_env(Path(a.env)), **os.environ}
    faltan = [k for k in ("SUPABASE_URL", "SUPABASE_CLAVE_PUBLICA", "SUPABASE_CLAVE") if not env.get(k)]
    if faltan:
        print(f"Faltan en el .env: {', '.join(faltan)}. Ver docs/NUBE.md, paso 5.")
        return 2
    if env["SUPABASE_CLAVE_PUBLICA"] == env["SUPABASE_CLAVE"]:
        print("FALLA: la clave pública es igual a la secreta. La pública es la anon/publishable.")
        return 1
    bien &= _imprimir(f"Proyecto {env['SUPABASE_URL']}",
                      revisar_proyecto(env["SUPABASE_URL"], env["SUPABASE_CLAVE_PUBLICA"], env["SUPABASE_CLAVE"]))
    print("Todo OK." if bien else "Hay fallas: revise la RLS (pegar de nuevo viaviva/supabase_esquema.sql).")
    return 0 if bien else 1


if __name__ == "__main__":
    sys.exit(main())
