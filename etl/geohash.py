"""Geohash (codificación) escrito a mano, sin dependencias.

Divide el mundo en celdas: cada carácter agrega 5 bits, alternando longitud y latitud.
Puntos cercanos comparten prefijo, así que el geohash sirve como llave de una tabla hash
para agrupar eventos cercanos en O(1) promedio por evento, en vez de O(n) comparando
cada evento contra todos los demás (O(n^2) en total).

Precisión 7 → celda de ~153 m x 153 m.
"""

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def codificar(lat: float, lon: float, precision: int = 7) -> str:
    lat_min, lat_max = -90.0, 90.0
    lon_min, lon_max = -180.0, 180.0
    codigo = []
    bit, ch, par = 0, 0, True  # par=True → se divide longitud
    while len(codigo) < precision:
        if par:
            medio = (lon_min + lon_max) / 2
            if lon >= medio:
                ch = (ch << 1) | 1
                lon_min = medio
            else:
                ch <<= 1
                lon_max = medio
        else:
            medio = (lat_min + lat_max) / 2
            if lat >= medio:
                ch = (ch << 1) | 1
                lat_min = medio
            else:
                ch <<= 1
                lat_max = medio
        par = not par
        bit += 1
        if bit == 5:
            codigo.append(_BASE32[ch])
            bit, ch = 0, 0
    return "".join(codigo)


if __name__ == "__main__":
    # Valor de referencia conocido (Wikipedia): (57.64911, 10.40744) → 'u4pruydqqvj'
    assert codificar(57.64911, 10.40744, 11) == "u4pruydqqvj"
    print("Plaza de Bolívar, Tunja:", codificar(5.5353, -73.3678))
