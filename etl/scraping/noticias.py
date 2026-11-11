"""Plantilla: noticias de cierres viales, obras y accidentes → tabla fuentes_externas.

Cómo agregar una fuente:
  1. Verificar a mano sus términos de uso y que robots.txt permita la URL
     (python -m etl.scraping.noticias --revisar lo comprueba por ustedes).
  2. Preferir RSS/Atom (tipo 'rss'). Si solo hay HTML, usar tipo 'html' con selectores CSS.
  3. Agregarla a FUENTES con habilitada=True.

Solo se guardan las entradas que pasan el filtro de palabras clave (clasificar()).
La ubicación (lat/lon/id_tramo) queda vacía: se completa en el paso de geocodificación del ETL.

Uso (desde via-viva/):
  etl\\.venv\\Scripts\\python -m etl.scraping.noticias --revisar   # solo revisa robots.txt y si responde
  etl\\.venv\\Scripts\\python -m etl.scraping.noticias             # descarga las fuentes habilitadas
"""
import argparse
import re
import unicodedata
from urllib.parse import urljoin

import feedparser
from bs4 import BeautifulSoup

from etl.db import conectar
from etl.scraping.comun import ClienteRespetuoso, NoPermitidoPorRobots, guardar, hash_contenido

# Revisado el 26-oct-2026 con --revisar. Volver a revisar antes de habilitar una fuente.
FUENTES = [
    {
        "nombre": "Gobernación de Boyacá (RSS)",
        "tipo": "rss",
        "url": "https://www.boyaca.gov.co/feed/",
        "habilitada": True,
        "nota": "robots.txt lo permite; fuente oficial; cubre vías departamentales.",
    },
    {
        "nombre": "Boyacá 7 Días (RSS)",
        "tipo": "rss",
        "url": "https://boyaca7dias.com.co/feed/",
        "habilitada": False,
        "nota": "robots.txt permite todo (26-oct y 10-nov). Sin página de términos; el pie dice «prohibida su "
                "reproducción total o parcial sin autorización»: se deja apagada hasta que el equipo decida "
                "(si se habilita, guardar solo titular, enlace y fecha). Ver docs/SCRAPING.md.",
    },
    {
        # Ejemplo de fuente HTML. Este sitio no publica robots.txt (devuelve su página),
        # responde lento y carga las noticias con JavaScript: con requests se leen 0 entradas.
        "nombre": "Alcaldía de Tunja (noticias)",
        "tipo": "html",
        "url": "https://www.tunja-boyaca.gov.co/noticias",
        "selector_item": "article",          # ajustar al HTML real
        "selector_titulo": "h2, h3",
        "selector_enlace": "a",
        "selector_resumen": "p",
        "habilitada": False,
        "nota": "Página hecha en JavaScript y con hCaptcha (10-nov): no se raspa; pedir los datos por oficio.",
    },
]

# Palabras clave por tipo (sin tildes, en minúscula). El orden importa: gana el primer tipo que coincida.
PALABRAS = {
    "accidente": ["accidente", "choque", "siniestro vial", "volcamiento", "atropell", "colision"],
    "cierre_vial": ["cierre", "cerrad", "desvio", "paso restringido", "restriccion vehicular",
                    "paso a un carril", "derrumbe", "deslizamiento", "via bloqueada"],
    "obra": ["hueco", "bache", "malla vial", "pavimentacion", "reparcheo", "parcheo",
             "mantenimiento vial", "rehabilitacion de la via"],
}
LUGARES = ["tunja"]  # para marcar si la noticia menciona la ciudad


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", texto.lower())


def clasificar(texto: str):
    t = normalizar(texto)
    for tipo, palabras in PALABRAS.items():
        if any(p in t for p in palabras):
            return tipo
    return None


def leer_rss(cliente, fuente) -> list[dict]:
    feed = feedparser.parse(cliente.get(fuente["url"]).content)
    entradas = []
    for e in feed.entries:
        resumen = BeautifulSoup(e.get("summary", ""), "html.parser").get_text(" ", strip=True)
        entradas.append({"titulo": e.get("title", ""), "enlace": e.get("link", fuente["url"]),
                         "resumen": resumen, "fecha": e.get("published") or e.get("updated")})
    return entradas


def leer_html(cliente, fuente) -> list[dict]:
    sopa = BeautifulSoup(cliente.get(fuente["url"]).text, "html.parser")
    entradas = []
    for item in sopa.select(fuente["selector_item"]):
        titulo = item.select_one(fuente["selector_titulo"])
        enlace = item.select_one(fuente["selector_enlace"])
        resumen = item.select_one(fuente["selector_resumen"])
        entradas.append({
            "titulo": titulo.get_text(" ", strip=True) if titulo else "",
            "enlace": urljoin(fuente["url"], enlace["href"]) if enlace and enlace.has_attr("href") else fuente["url"],
            "resumen": resumen.get_text(" ", strip=True) if resumen else "",
            "fecha": None,
        })
    return entradas


LECTORES = {"rss": leer_rss, "html": leer_html}


def revisar(cliente):
    for f in FUENTES:
        print(f"- {f['nombre']} ({'habilitada' if f['habilitada'] else 'deshabilitada'})  {f['url']}")
        permitido = cliente.permitido(f["url"])
        print(f"    {cliente.estado(f['url'])}; {'permitido' if permitido else 'NO permitido'}")
        if not permitido:
            continue
        try:
            entradas = LECTORES[f["tipo"]](cliente, f)
            relevantes = sum(clasificar(f"{e['titulo']} {e['resumen']}") is not None for e in entradas)
            print(f"    responde: {len(entradas)} entradas, {relevantes} relevantes")
        except Exception as e:
            print(f"    falla: {type(e).__name__}: {str(e)[:120]}")


def ejecutar(cliente) -> dict:
    """Lee las fuentes habilitadas; devuelve {'nuevas', 'leidas', 'omitidas'} (lo registra etl.scraping.diario)."""
    con = conectar()
    total = {"nuevas": 0, "leidas": 0, "omitidas": 0}
    for f in [f for f in FUENTES if f["habilitada"]]:
        try:
            entradas = LECTORES[f["tipo"]](cliente, f)
        except NoPermitidoPorRobots:
            print(f"  {f['nombre']}: robots.txt ya no lo permite, se omite")
            total["omitidas"] += 1
            continue
        registros = []
        for e in entradas:
            texto = f"{e['titulo']} {e['resumen']}"
            tipo = clasificar(texto)
            if tipo is None:
                continue
            registros.append({
                "fuente": f["nombre"],
                "tipo": tipo,
                "url": e["enlace"],
                "titulo": e["titulo"],
                "contenido": e["resumen"][:2000],
                "ts_dato": e["fecha"],
                "extra_json": {"menciona_tunja": any(l in normalizar(texto) for l in LUGARES)},
                "hash_contenido": hash_contenido(f["nombre"], e["enlace"], e["titulo"]),
            })
        nuevos, _ = guardar(con, registros)
        print(f"  {f['nombre']}: {len(entradas)} entradas leídas, {len(registros)} relevantes, {nuevos} nuevas")
        total["nuevas"] += nuevos
        total["leidas"] += len(entradas)
    return total


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--revisar", action="store_true", help="solo revisa robots.txt y si cada fuente responde")
    args = p.parse_args()
    cliente = ClienteRespetuoso()
    revisar(cliente) if args.revisar else ejecutar(cliente)


if __name__ == "__main__":
    main()
