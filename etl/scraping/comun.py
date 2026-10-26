"""Herramientas comunes de scraping responsable.

Reglas que aplica este módulo (CLAUDE.md, sección 9 del diseño):
  * Consulta robots.txt de cada dominio antes de pedir una URL; si no está permitido, no la pide.
  * Respeta Crawl-delay (o 2 s por defecto) entre peticiones al mismo dominio.
  * Se identifica con un User-Agent propio (SCRAPER_USER_AGENT en .env).
  * Guarda la URL de origen de cada dato (trazabilidad) y evita duplicados con un hash.
"""
import hashlib
import json
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

from etl.config import USER_AGENT
from etl.db import ahora_utc

ESPERA_MINIMA_S = 2.0


class NoPermitidoPorRobots(Exception):
    pass


class ClienteRespetuoso:
    def __init__(self, user_agent: str = USER_AGENT, timeout: int = 60):
        self.user_agent = user_agent
        self.timeout = timeout
        self.sesion = requests.Session()
        self.sesion.headers["User-Agent"] = user_agent
        self._robots = {}        # dominio -> RobotFileParser
        self.estado_robots = {}  # dominio -> texto que explica cómo se leyó robots.txt
        self._ultima = {}        # dominio -> instante de la última petición

    def _parser(self, url: str):
        p = urlparse(url)
        dominio = f"{p.scheme}://{p.netloc}"
        if dominio not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.sesion.get(f"{dominio}/robots.txt", timeout=self.timeout)
                tipo = r.headers.get("content-type", "")
                if r.status_code == 200 and "html" in tipo:
                    rp.allow_all = True      # el sitio devuelve su página, no un robots.txt
                    estado = "no publica robots.txt (devuelve HTML)"
                elif r.status_code == 200:
                    rp.parse(r.text.splitlines())
                    estado = "robots.txt leído"
                elif r.status_code in (401, 403):
                    rp.disallow_all = True   # acceso restringido → no se rastrea
                    estado = f"robots.txt restringido ({r.status_code})"
                else:
                    rp.allow_all = True      # 404 u otro: no hay reglas publicadas
                    estado = f"sin robots.txt ({r.status_code})"
            except requests.RequestException as e:
                rp.disallow_all = True       # si no se puede leer robots.txt, se es conservador
                estado = f"no se pudo leer robots.txt ({type(e).__name__}); se trata como NO permitido"
            self._robots[dominio] = rp
            self.estado_robots[dominio] = estado
        return dominio, self._robots[dominio]

    def estado(self, url: str) -> str:
        dominio, _ = self._parser(url)
        return self.estado_robots[dominio]

    def permitido(self, url: str) -> bool:
        _, rp = self._parser(url)
        return rp.can_fetch(self.user_agent, url)

    def get(self, url: str, **kwargs) -> requests.Response:
        dominio, rp = self._parser(url)
        if not rp.can_fetch(self.user_agent, url):
            raise NoPermitidoPorRobots(url)
        espera = max(float(rp.crawl_delay(self.user_agent) or 0), ESPERA_MINIMA_S)
        transcurrido = time.monotonic() - self._ultima.get(dominio, 0)
        if transcurrido < espera:
            time.sleep(espera - transcurrido)
        r = self.sesion.get(url, timeout=self.timeout, **kwargs)
        self._ultima[dominio] = time.monotonic()
        r.raise_for_status()
        return r


def hash_contenido(*campos) -> str:
    return hashlib.sha256("|".join(str(c) for c in campos).encode("utf-8")).hexdigest()


COLUMNAS = ["fuente", "tipo", "url", "titulo", "contenido", "variable", "valor", "unidad",
            "ts_dato", "lat", "lon", "id_tramo", "extra_json", "hash_contenido"]


def guardar(con, registros: list[dict], actualizar: bool = False) -> tuple[int, int]:
    """Inserta registros en fuentes_externas. Devuelve (nuevos, actualizados).

    actualizar=True: si el hash ya existe se reemplazan valor y extra_json
    (útil para clima: un día parcial se completa en la siguiente corrida).
    """
    captura = ahora_utc()
    nuevos = actualizados = 0
    with con:
        for reg in registros:
            reg = dict(reg)
            if reg.get("extra_json") is not None:
                reg["extra_json"] = json.dumps(reg["extra_json"], ensure_ascii=False)
            fila = [reg.get(c) for c in COLUMNAS]
            existe = con.execute("SELECT 1 FROM fuentes_externas WHERE hash_contenido = ?",
                                 (reg["hash_contenido"],)).fetchone()
            if existe and actualizar:
                con.execute(
                    "UPDATE fuentes_externas SET valor = ?, extra_json = ?, ts_captura = ? "
                    "WHERE hash_contenido = ?",
                    (reg.get("valor"), reg.get("extra_json"), captura, reg["hash_contenido"]))
                actualizados += 1
            elif not existe:
                con.execute(
                    f"INSERT INTO fuentes_externas ({', '.join(COLUMNAS)}, ts_captura) "
                    f"VALUES ({', '.join('?' * len(COLUMNAS))}, ?)",
                    fila + [captura])
                nuevos += 1
    return nuevos, actualizados
