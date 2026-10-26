package viaviva.estructuras;

/**
 * Geohash: codifica (lat, lon) en una cadena; puntos cercanos comparten prefijo.
 * Es la misma función que etl/geohash.py, así las llaves coinciden entre Python y Java.
 *
 * <p>Precisión 6 ≈ celda de 1,2 km × 0,6 km; precisión 7 ≈ 153 m × 153 m (la que usa el tablero).</p>
 */
public final class Geohash {

    private static final String BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz";

    private Geohash() {
    }

    public static String codificar(double lat, double lon, int precision) {
        double latMin = -90, latMax = 90, lonMin = -180, lonMax = 180;
        StringBuilder sb = new StringBuilder(precision);
        boolean par = true;   // true = se divide longitud
        int bit = 0, ch = 0;
        while (sb.length() < precision) {
            if (par) {
                double medio = (lonMin + lonMax) / 2;
                if (lon >= medio) { ch = (ch << 1) | 1; lonMin = medio; } else { ch <<= 1; lonMax = medio; }
            } else {
                double medio = (latMin + latMax) / 2;
                if (lat >= medio) { ch = (ch << 1) | 1; latMin = medio; } else { ch <<= 1; latMax = medio; }
            }
            par = !par;
            if (++bit == 5) {
                sb.append(BASE32.charAt(ch));
                bit = 0;
                ch = 0;
            }
        }
        return sb.toString();
    }

    /** Devuelve {latMin, latMax, lonMin, lonMax} de la celda. */
    public static double[] limites(String geohash) {
        double latMin = -90, latMax = 90, lonMin = -180, lonMax = 180;
        boolean par = true;
        for (int i = 0; i < geohash.length(); i++) {
            int valor = BASE32.indexOf(geohash.charAt(i));
            for (int b = 4; b >= 0; b--) {
                int bitActual = (valor >> b) & 1;
                if (par) {
                    double medio = (lonMin + lonMax) / 2;
                    if (bitActual == 1) lonMin = medio; else lonMax = medio;
                } else {
                    double medio = (latMin + latMax) / 2;
                    if (bitActual == 1) latMin = medio; else latMax = medio;
                }
                par = !par;
            }
        }
        return new double[]{latMin, latMax, lonMin, lonMax};
    }

    /** La celda y sus 8 vecinas (útil para buscar cerca de un borde de celda). */
    public static String[] celdaYVecinas(String geohash) {
        double[] l = limites(geohash);
        double dLat = l[1] - l[0], dLon = l[3] - l[2];
        double latC = (l[0] + l[1]) / 2, lonC = (l[2] + l[3]) / 2;
        String[] celdas = new String[9];
        int k = 0;
        for (int i = -1; i <= 1; i++) {
            for (int j = -1; j <= 1; j++) {
                celdas[k++] = codificar(latC + i * dLat, lonC + j * dLon, geohash.length());
            }
        }
        return celdas;
    }
}
