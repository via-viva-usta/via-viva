"""Cronómetro del iPhone (vueltas) → <recorrido>_etiquetas.csv (t_s,clase) para etl/recorridos.py.

El copiloto inicia el cronómetro del iPhone EN EL MISMO INSTANTE que oprime play en phyphox y oprime "Vuelta" cada vez
que la llanta pasa por algo. En iOS cada vuelta muestra su DURACIÓN (desde la vuelta anterior), no el tiempo acumulado:
este programa suma las duraciones. Se transcriben a un .txt, una vuelta por línea y EN ORDEN (la vuelta 1 primero):

    1:02.40 hueco          (también: 62.4 hueco · 00:01:02,40 hueco · "Vuelta 1  01:02,40  hueco")
    0:33.10 resalto
    0:20.00 parada_inicio  (el carro se detuvo: semáforo, trancón)
    0:45.00 parada_fin     (arrancó otra vez)
    # las líneas con # se ignoran

Clases: hueco, resalto, impacto_fuerte, obstaculo, otro (acepta bache, reductor, policia...). parada_inicio y
parada_fin NO son eventos: marcan tramos con el carro detenido, donde etl/recorridos.py no busca huecos.
Si se copió la lista tal como la muestra el iPhone (la vuelta más reciente arriba), usar --invertir.

Uso (desde via-viva/):
  analysis\\.venv\\Scripts\\python analysis\\vueltas_a_etiquetas.py data\\raw\\phyphox\\2026-11-06_ruta1_pipe_vueltas.txt
  → escribe data\\raw\\phyphox\\2026-11-06_ruta1_pipe_etiquetas.csv (el nombre sale del .txt sin "_vueltas")
Ejemplo: analysis/ejemplos/vueltas_ejemplo.txt
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from pathlib import Path

CLASES = ["hueco", "resalto", "impacto_fuerte", "obstaculo", "otro"]
PARADAS = ["parada_inicio", "parada_fin"]
SINONIMOS = {"bache": "hueco", "hueco": "hueco", "resalto": "resalto", "reductor": "resalto", "policia": "resalto",
             "policiaacostado": "resalto", "impacto": "impacto_fuerte", "impactofuerte": "impacto_fuerte",
             "golpe": "impacto_fuerte", "obstaculo": "obstaculo", "otro": "otro", "paradainicio": "parada_inicio",
             "parada": "parada_inicio", "inicioparada": "parada_inicio", "paradafin": "parada_fin",
             "finparada": "parada_fin", "arranque": "parada_fin"}
_DURACION = re.compile(r"^(?:(\d+):)?(?:(\d+):)?(\d+(?:[.,]\d+)?)$")


def _clave(t: str) -> str:
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", t)


def duracion_s(texto: str) -> float:
    """'1:02.40' → 62.4 · '62,4' → 62.4 · '1:00:05' → 3605."""
    m = _DURACION.match(texto.strip())
    if not m:
        raise ValueError(f"duración no válida: {texto!r} (usar m:ss.cc o segundos)")
    a, b, s = m.groups()
    seg = float(s.replace(",", "."))
    if a is not None and b is not None:          # h:mm:ss
        return int(a) * 3600 + int(b) * 60 + seg
    if a is not None:                            # m:ss
        return int(a) * 60 + seg
    return seg


def leer_vueltas(lineas: list[str]) -> list[tuple[float, str, int]]:
    """[(duración_s, clase, número de línea)] en el orden del archivo."""
    vueltas = []
    for n, linea in enumerate(lineas, 1):
        linea = linea.split("#", 1)[0].strip()
        if not linea:
            continue
        linea = re.sub(r"^(vuelta|lap)\s*\d+\s+", "", linea, flags=re.I)   # "Vuelta 3  00:12,34 hueco"
        partes = linea.split(None, 1)
        if len(partes) < 2:
            raise ValueError(f"línea {n}: falta la clase en {linea!r} (formato: 'duración clase')")
        clase = SINONIMOS.get(_clave(partes[1]))
        if clase is None:
            raise ValueError(f"línea {n}: clase desconocida {partes[1]!r}; válidas: {', '.join(CLASES + PARADAS)}")
        vueltas.append((duracion_s(partes[0]), clase, n))
    return vueltas


def a_etiquetas(vueltas: list[tuple[float, str, int]]) -> list[tuple[float, str]]:
    """Suma las duraciones (tiempo acumulado = t_s desde el play de phyphox) y revisa que las paradas cierren."""
    t, filas, en_parada = 0.0, [], False
    for d, clase, n in vueltas:
        t += d
        if clase == "parada_inicio":
            if en_parada:
                raise ValueError(f"línea {n}: parada_inicio sin cerrar la parada anterior")
            en_parada = True
        elif clase == "parada_fin":
            if not en_parada:
                raise ValueError(f"línea {n}: parada_fin sin parada_inicio")
            en_parada = False
        filas.append((round(t, 2), clase))
    if en_parada:
        raise ValueError("la última parada no tiene parada_fin")
    return filas


def intervalos_parada(t_s, clases) -> list[tuple[float, float]]:
    """[(inicio, fin)] de las paradas en una tabla t_s,clase (la usa etl/recorridos.py)."""
    ints, ini = [], None
    for t, c in sorted(zip(t_s, clases)):
        if c == "parada_inicio":
            ini = t
        elif c == "parada_fin" and ini is not None:
            ints.append((ini, t))
            ini = None
    return ints


def convertir(entrada: Path, salida: Path | None = None, invertir: bool = False) -> Path:
    lineas = entrada.read_text(encoding="utf-8-sig").splitlines()
    vueltas = leer_vueltas(lineas)
    if invertir:
        vueltas = vueltas[::-1]
    filas = a_etiquetas(vueltas)
    if salida is None:
        base = re.sub(r"_vueltas$", "", entrada.stem)
        salida = entrada.with_name(f"{base}_etiquetas.csv")
    with salida.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "clase"])
        w.writerows(filas)
    return salida


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path, help="archivo .txt con una vuelta por línea")
    ap.add_argument("--salida", type=Path, default=None)
    ap.add_argument("--invertir", action="store_true", help="la lista se copió con la vuelta más reciente arriba")
    a = ap.parse_args()
    try:
        salida = convertir(a.entrada, a.salida, a.invertir)
    except ValueError as e:
        sys.exit(f"ERROR: {e}")
    filas = list(csv.reader(salida.open(encoding="utf-8")))[1:]
    eventos = [f for f in filas if f[1] not in PARADAS]
    print(f"Escrito {salida}: {len(eventos)} eventos y {(len(filas) - len(eventos)) // 2} paradas; "
          f"última marca en {filas[-1][0] if filas else 0} s")


if __name__ == "__main__":
    main()
