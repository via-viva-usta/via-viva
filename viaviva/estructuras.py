"""Estructuras de datos del servidor de la Pi, escritas a mano (Estructuras de Datos).

Reemplazan a las del tablero Java (`dashboard-java/src/viaviva/estructuras/`, que se conserva) con la misma
complejidad. Python trae `dict`, `heapq` y `deque`, pero aquí se implementan para poder justificar cada costo:

| Estructura        | Dónde se usa en la Pi                                         | Operación              | Costo            |
|-------------------|---------------------------------------------------------------|------------------------|------------------|
| BuferCircular     | Últimas muestras (gráfica en vivo, ventana pico a pico)       | agregar / leer i       | O(1)             |
| Cola              | Frontera del BFS                                              | encolar / desencolar   | O(1) amortizado  |
| TablaHash         | Conteo de peligros por tramo, tramos por id, índice geohash   | poner / obtener        | O(1) promedio    |
| MonticuloMax      | Top-10 de riesgo y orden de atención de peligros              | construir / extraer    | O(n) / O(log n)  |
| GrafoCalles (BFS) | Corredor a ≤ k intersecciones y zonas de riesgo conectadas    | BFS                    | O(V + E)         |
| IndiceGeohash     | Asignar un evento al tramo más cercano sin internet           | consulta               | O(1) + candidatos|
"""
from __future__ import annotations

import math
from typing import Any, Callable, Generic, Iterable, Iterator, TypeVar

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")


# ------------------------------------------------------------------------------------------------ búfer circular
class BuferCircular(Generic[T]):
    """Arreglo de tamaño fijo; al llenarse sobrescribe lo más viejo. Memoria O(capacidad), nunca crece.

    Es la misma idea del búfer del nodo ESP32 (`firmware/nodo-sensores/include/bufer_circular.h`): la adquisición
    escribe sin pedir memoria nueva, así que no hay pausas del recolector de basura por crecer listas.
    """

    def __init__(self, capacidad: int):
        if capacidad < 1:
            raise ValueError("capacidad debe ser ≥ 1")
        self._datos: list[Any] = [None] * capacidad
        self._cap, self._inicio, self._n = capacidad, 0, 0
        self.sobrescritos = 0                     # cuántos datos se perdieron por llenarse (diagnóstico)

    def agregar(self, x: T) -> None:              # O(1)
        fin = (self._inicio + self._n) % self._cap
        self._datos[fin] = x
        if self._n < self._cap:
            self._n += 1
        else:
            self._inicio = (self._inicio + 1) % self._cap
            self.sobrescritos += 1

    def __len__(self) -> int:
        return self._n

    def __getitem__(self, i: int) -> T:           # O(1); 0 = el más viejo, -1 = el más nuevo
        if i < 0:
            i += self._n
        if not 0 <= i < self._n:
            raise IndexError(i)
        return self._datos[(self._inicio + i) % self._cap]

    def __iter__(self) -> Iterator[T]:
        for i in range(self._n):
            yield self._datos[(self._inicio + i) % self._cap]

    def ultimos(self, k: int) -> list[T]:          # O(k)
        k = max(0, min(k, self._n))
        return [self[self._n - k + i] for i in range(k)]

    def lleno(self) -> bool:
        return self._n == self._cap


# ------------------------------------------------------------------------------------------------ cola
class Cola(Generic[T]):
    """Cola FIFO sobre una lista con índice de cabeza: encolar y desencolar O(1) amortizado.

    `list.pop(0)` sería O(n) porque corre todos los elementos; aquí la cabeza avanza y la lista se compacta solo
    cuando la mitad ya fue consumida (costo amortizado O(1)).
    """

    def __init__(self):
        self._d: list[T] = []
        self._cabeza = 0

    def encolar(self, x: T) -> None:
        self._d.append(x)

    def desencolar(self) -> T:
        if self._cabeza >= len(self._d):
            raise IndexError("cola vacía")
        x = self._d[self._cabeza]
        self._cabeza += 1
        if self._cabeza > 32 and self._cabeza * 2 >= len(self._d):
            self._d, self._cabeza = self._d[self._cabeza:], 0
        return x

    def __len__(self) -> int:
        return len(self._d) - self._cabeza


# ------------------------------------------------------------------------------------------------ tabla hash
def _mezclar64(x: int) -> int:
    """splitmix64: reparte bien enteros consecutivos (los id de tramo lo son)."""
    x = (x + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    return x ^ (x >> 31)


def hash_llave(llave) -> int:
    """Hash propio y estable entre corridas (el `hash()` de Python cambia los textos en cada proceso)."""
    if isinstance(llave, bool):
        llave = int(llave)
    if isinstance(llave, int):
        return _mezclar64(llave & 0xFFFFFFFFFFFFFFFF)
    if isinstance(llave, str):                    # FNV-1a de 64 bits sobre los bytes UTF-8
        h = 0xCBF29CE484222325
        for b in llave.encode("utf-8"):
            h = ((h ^ b) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
        return h
    if isinstance(llave, tuple):
        h = 0x345678
        for parte in llave:
            h = _mezclar64(h ^ hash_llave(parte))
        return h
    raise TypeError(f"llave no soportada: {type(llave).__name__}")


class TablaHash(Generic[K, V]):
    """Tabla hash con encadenamiento separado. Factor de carga ≤ 0,75: al pasarlo duplica las cubetas (rehash O(n),
    amortizado O(1) por inserción). poner / obtener / quitar: O(1) promedio, O(n) peor caso (todo en una cubeta)."""

    CARGA_MAX = 0.75

    def __init__(self, capacidad: int = 16):
        cap = 8
        while cap < capacidad:
            cap *= 2                              # potencia de 2: el índice es un AND, no una división
        self._cubetas: list[list[list]] = [[] for _ in range(cap)]
        self._n = 0

    def _cubeta(self, llave) -> list:
        return self._cubetas[hash_llave(llave) & (len(self._cubetas) - 1)]

    def poner(self, llave: K, valor: V) -> None:
        cub = self._cubeta(llave)
        for par in cub:
            if par[0] == llave:
                par[1] = valor
                return
        cub.append([llave, valor])
        self._n += 1
        if self._n > self.CARGA_MAX * len(self._cubetas):
            self._crecer()

    def obtener(self, llave: K, defecto: V | None = None) -> V | None:
        for k, v in self._cubeta(llave):
            if k == llave:
                return v
        return defecto

    def contiene(self, llave: K) -> bool:
        return any(k == llave for k, _ in self._cubeta(llave))

    def quitar(self, llave: K) -> bool:
        cub = self._cubeta(llave)
        for i, par in enumerate(cub):
            if par[0] == llave:
                cub.pop(i)
                self._n -= 1
                return True
        return False

    def sumar(self, llave: K, cantidad: int = 1) -> int:
        """Contador: obtener + poner en una sola búsqueda."""
        cub = self._cubeta(llave)
        for par in cub:
            if par[0] == llave:
                par[1] += cantidad
                return par[1]
        cub.append([llave, cantidad])
        self._n += 1
        if self._n > self.CARGA_MAX * len(self._cubetas):
            self._crecer()
        return cantidad

    def _crecer(self) -> None:
        viejas = self._cubetas
        self._cubetas = [[] for _ in range(len(viejas) * 2)]
        for cub in viejas:
            for k, v in cub:
                self._cubeta(k).append([k, v])

    def __len__(self) -> int:
        return self._n

    def items(self) -> Iterator[tuple[K, V]]:
        for cub in self._cubetas:
            for k, v in cub:
                yield k, v

    def cubeta_mas_larga(self) -> int:            # diagnóstico de colisiones
        return max((len(c) for c in self._cubetas), default=0)


# ------------------------------------------------------------------------------------------------ montículo
class MonticuloMax(Generic[T]):
    """Montículo binario de máximos en un arreglo (hijos de i en 2i+1 y 2i+2).

    construir (heapify de abajo hacia arriba): O(n) · insertar y extraer: O(log n) · top-k: O(n + k log n),
    mejor que ordenar todo (O(n log n)) cuando k = 10 y n = 5 775 tramos.
    `clave(x)` devuelve una tupla comparable: mayor = sale primero.
    """

    def __init__(self, clave: Callable[[T], Any], elementos: Iterable[T] = ()):
        self._clave = clave
        self._a: list[tuple[Any, T]] = [(clave(x), x) for x in elementos]
        for i in range(len(self._a) // 2 - 1, -1, -1):
            self._bajar(i)

    def _subir(self, i: int) -> None:
        a = self._a
        while i > 0:
            p = (i - 1) // 2
            if a[i][0] <= a[p][0]:
                break
            a[i], a[p] = a[p], a[i]
            i = p

    def _bajar(self, i: int) -> None:
        a, n = self._a, len(self._a)
        while True:
            mayor, izq, der = i, 2 * i + 1, 2 * i + 2
            if izq < n and a[izq][0] > a[mayor][0]:
                mayor = izq
            if der < n and a[der][0] > a[mayor][0]:
                mayor = der
            if mayor == i:
                return
            a[i], a[mayor] = a[mayor], a[i]
            i = mayor

    def insertar(self, x: T) -> None:
        self._a.append((self._clave(x), x))
        self._subir(len(self._a) - 1)

    def extraer(self) -> T:
        if not self._a:
            raise IndexError("montículo vacío")
        tope = self._a[0][1]
        ultimo = self._a.pop()
        if self._a:
            self._a[0] = ultimo
            self._bajar(0)
        return tope

    def ver(self) -> T:
        return self._a[0][1]

    def __len__(self) -> int:
        return len(self._a)


def top_k(elementos: Iterable[T], k: int, clave: Callable[[T], Any]) -> list[T]:
    m = MonticuloMax(clave, elementos)
    return [m.extraer() for _ in range(min(k, len(m)))]


# ------------------------------------------------------------------------------------------------ grafo de calles
class GrafoCalles:
    """Grafo no dirigido: nodos = intersecciones OSM, aristas = tramos. Lista de adyacencia en una TablaHash.

    Memoria O(V + E). Se trata como no dirigido aunque haya calles de un sentido: interesa la cercanía física de
    un peligro (zona de influencia), no la ruta de un carro.
    """

    def __init__(self):
        self._ady: TablaHash[int, list[tuple[int, int]]] = TablaHash()   # nodo → [(vecino, id_tramo)]
        self._extremos: TablaHash[int, tuple[int, int]] = TablaHash()    # id_tramo → (u, v)
        self.n_aristas = 0

    def agregar_tramo(self, id_tramo: int, u: int, v: int) -> None:    # O(1) promedio
        for a, b in ((u, v), (v, u)):
            lista = self._ady.obtener(a)
            if lista is None:
                lista = []
                self._ady.poner(a, lista)
            lista.append((b, id_tramo))
        self._extremos.poner(id_tramo, (u, v))
        self.n_aristas += 1

    def num_nodos(self) -> int:
        return len(self._ady)

    def corredor(self, id_tramo: int, max_saltos: int) -> dict[int, int]:
        """BFS desde los dos extremos del tramo: {id_tramo: intersecciones de distancia} con distancia ≤ max_saltos.
        El tramo de origen queda con 0. O(V + E) en el peor caso; en la práctica solo lo alcanzado."""
        extremos = self._extremos.obtener(id_tramo)
        if extremos is None:
            return {}
        dist_nodo: TablaHash[int, int] = TablaHash()
        cola: Cola[int] = Cola()
        for n in extremos:
            dist_nodo.poner(n, 0)
            cola.encolar(n)
        tramos = {id_tramo: 0}
        while len(cola):
            n = cola.desencolar()
            d = dist_nodo.obtener(n)
            if d >= max_saltos:
                continue
            for vecino, t in self._ady.obtener(n, []):
                if t not in tramos:
                    tramos[t] = d + 1
                if not dist_nodo.contiene(vecino):
                    dist_nodo.poner(vecino, d + 1)
                    cola.encolar(vecino)
        return tramos

    def zonas(self, tramos_marcados: set[int]) -> list[list[int]]:
        """Componentes conexas formadas solo por tramos marcados (p. ej. riesgo ≥ umbral), con BFS. O(V + E).
        Devuelve las zonas de mayor a menor número de tramos."""
        visto: set[int] = set()
        zonas = []
        for inicio in tramos_marcados:
            if inicio in visto or self._extremos.obtener(inicio) is None:
                continue
            zona, cola = [], Cola()
            cola.encolar(inicio)
            visto.add(inicio)
            while len(cola):
                t = cola.desencolar()
                zona.append(t)
                for n in self._extremos.obtener(t):
                    for _, t2 in self._ady.obtener(n, []):
                        if t2 in tramos_marcados and t2 not in visto:
                            visto.add(t2)
                            cola.encolar(t2)
            zonas.append(sorted(zona))
        return sorted(zonas, key=len, reverse=True)


# ------------------------------------------------------------------------------------------------ geohash
_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"
_VALOR = {c: i for i, c in enumerate(_BASE32)}
R_TIERRA_M = 6_371_000.0


def geohash(lat: float, lon: float, precision: int = 7) -> str:
    """Igual a `etl/geohash.py` (prueba en tests/test_pi_estructuras.py). Precisión 7 ≈ celda de 153 m × 153 m."""
    la, lo = [-90.0, 90.0], [-180.0, 180.0]
    salida, bits, ch, par = [], 0, 0, True
    while len(salida) < precision:
        rango, v = (lo, lon) if par else (la, lat)
        medio = (rango[0] + rango[1]) / 2
        if v >= medio:
            ch, rango[0] = (ch << 1) | 1, medio
        else:
            ch, rango[1] = ch << 1, medio
        par, bits = not par, bits + 1
        if bits == 5:
            salida.append(_BASE32[ch])
            bits, ch = 0, 0
    return "".join(salida)


def caja_geohash(g: str) -> tuple[float, float, float, float]:
    """(lat_min, lat_max, lon_min, lon_max) de la celda."""
    la, lo, par = [-90.0, 90.0], [-180.0, 180.0], True
    for c in g:
        v = _VALOR[c]
        for desplaz in range(4, -1, -1):
            rango = lo if par else la
            medio = (rango[0] + rango[1]) / 2
            if (v >> desplaz) & 1:
                rango[0] = medio
            else:
                rango[1] = medio
            par = not par
    return la[0], la[1], lo[0], lo[1]


def vecinos_geohash(g: str) -> list[str]:
    """La celda y sus 8 vecinas (centro de la celda ± un ancho). O(precisión)."""
    a, b, c, d = caja_geohash(g)
    dlat, dlon = b - a, d - c
    clat, clon = (a + b) / 2, (c + d) / 2
    return [geohash(clat + i * dlat, clon + j * dlon, len(g)) for i in (-1, 0, 1) for j in (-1, 0, 1)]


def distancia_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Equirectangular: error < 0,1 % a escala de ciudad, más barata que haversine."""
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return R_TIERRA_M * math.hypot(x, y)


def distancia_a_segmento_m(lat, lon, a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distancia de un punto al segmento a–b (lat, lon) en un plano local alrededor del punto."""
    k = math.cos(math.radians(lat))
    ax, ay = math.radians(a[1] - lon) * k, math.radians(a[0] - lat)
    bx, by = math.radians(b[1] - lon) * k, math.radians(b[0] - lat)
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, -(ax * dx + ay * dy) / l2))
    return R_TIERRA_M * math.hypot(ax + t * dx, ay + t * dy)


def leer_wkt_linea(wkt: str) -> list[tuple[float, float]]:
    """'LINESTRING (lon lat, lon lat, ...)' → [(lat, lon), ...]."""
    dentro = wkt[wkt.index("(") + 1: wkt.rindex(")")].replace("(", "").replace(")", "")
    puntos = []
    for par in dentro.split(","):
        lon, lat = par.split()[:2]
        puntos.append((float(lat), float(lon)))
    return puntos


class IndiceGeohash:
    """Índice espacial: celda geohash-7 → tramos que pasan por ella (TablaHash). Ajuste de un punto a su calle:
    revisar la celda y sus 8 vecinas (cubre ≥ 150 m alrededor) en vez de los 5 775 tramos: O(1) + candidatos."""

    PRECISION = 7

    def __init__(self):
        self._celdas: TablaHash[str, list[int]] = TablaHash(4096)
        self._geom: TablaHash[int, list[tuple[float, float]]] = TablaHash(8192)

    def agregar(self, id_tramo: int, puntos: list[tuple[float, float]]) -> None:
        self._geom.poner(id_tramo, puntos)
        celdas = set()
        for i, p in enumerate(puntos):          # vértices + puntos intermedios cada ~50 m (tramos largos y rectos)
            celdas.add(geohash(p[0], p[1], self.PRECISION))
            if i:
                q = puntos[i - 1]
                pasos = int(distancia_m(q[0], q[1], p[0], p[1]) // 50)
                for s in range(1, pasos + 1):
                    f = s / (pasos + 1)
                    celdas.add(geohash(q[0] + f * (p[0] - q[0]), q[1] + f * (p[1] - q[1]), self.PRECISION))
        for c in celdas:
            lista = self._celdas.obtener(c)
            if lista is None:
                self._celdas.poner(c, [id_tramo])
            else:
                lista.append(id_tramo)

    def __len__(self) -> int:
        return len(self._geom)

    def mas_cercano(self, lat: float, lon: float, max_m: float = 25.0) -> tuple[int | None, float]:
        candidatos = set()
        for c in vecinos_geohash(geohash(lat, lon, self.PRECISION)):
            candidatos.update(self._celdas.obtener(c, []))
        mejor, d_mejor = None, math.inf
        for t in candidatos:
            pts = self._geom.obtener(t)
            for a, b in zip(pts, pts[1:]):
                d = distancia_a_segmento_m(lat, lon, a, b)
                if d < d_mejor:
                    mejor, d_mejor = t, d
        return (mejor, d_mejor) if d_mejor <= max_m else (None, d_mejor)
