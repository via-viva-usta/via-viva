package viaviva.estructuras;

import java.util.ArrayList;
import java.util.List;
import viaviva.modelo.Proyeccion;
import viaviva.modelo.Tramo;

/**
 * Índice espacial: tabla hash de celdas geohash → tramos que pasan por la celda.
 *
 * <p>Para encontrar el tramo más cercano a un clic, en vez de medir la distancia a los n tramos
 * (fuerza bruta, O(n)), se miran solo los tramos de la celda del clic y sus 8 vecinas:
 * O(1) promedio para encontrar las celdas + O(m) para los m tramos de esas celdas, con m mucho menor que n.</p>
 */
public class IndiceGeohash {

    private final int precision;
    private final TablaHash<String, List<Tramo>> celdas = new TablaHash<>(1024);
    private final List<Tramo> todos = new ArrayList<>();
    private long comparacionesUltimaBusqueda;

    public IndiceGeohash(int precision) {
        this.precision = precision;
    }

    /** Separación de las muestras sobre cada segmento: menor que el lado de la celda de precisión 7 (~153 m). */
    private static final double PASO_M = 50.0;

    /**
     * Agrega el tramo a cada celda por la que pasa. No basta con las celdas de los vértices:
     * un segmento largo y recto puede cruzar una celda sin tener vértices en ella. Por eso cada
     * segmento se muestrea cada {@link #PASO_M} metros (los tramos ya deben estar proyectados).
     */
    public void insertar(Tramo t) {
        todos.add(t);
        TablaHash<String, Boolean> yaPuesto = new TablaHash<>();
        agregarACelda(t, t.lats[0], t.lons[0], yaPuesto);
        for (int i = 0; i + 1 < t.lats.length; i++) {
            double largo = Math.hypot(t.xs[i + 1] - t.xs[i], t.ys[i + 1] - t.ys[i]);
            int pasos = Math.max(1, (int) Math.ceil(largo / PASO_M));
            for (int k = 1; k <= pasos; k++) {
                double f = (double) k / pasos;
                agregarACelda(t, t.lats[i] + f * (t.lats[i + 1] - t.lats[i]),
                        t.lons[i] + f * (t.lons[i + 1] - t.lons[i]), yaPuesto);
            }
        }
    }

    private void agregarACelda(Tramo t, double lat, double lon, TablaHash<String, Boolean> yaPuesto) {
        String c = Geohash.codificar(lat, lon, precision);
        if (yaPuesto.contiene(c)) return;
        yaPuesto.poner(c, true);
        List<Tramo> lista = celdas.obtener(c);
        if (lista == null) {
            lista = new ArrayList<>();
            celdas.poner(c, lista);
        }
        lista.add(t);
    }

    /** Tramo más cercano usando el índice (celda + 8 vecinas). null si no hay ninguno a ≤ maxMetros. */
    public Tramo masCercano(double lat, double lon, Proyeccion p, double maxMetros) {
        comparacionesUltimaBusqueda = 0;
        double[] xy = p.aMetros(lat, lon);
        Tramo mejor = null;
        double mejorD = maxMetros;
        for (String c : Geohash.celdaYVecinas(Geohash.codificar(lat, lon, precision))) {
            List<Tramo> lista = celdas.obtener(c);
            if (lista == null) continue;
            for (Tramo t : lista) {
                comparacionesUltimaBusqueda++;
                double d = distanciaAPolilinea(xy[0], xy[1], t);
                if (d < mejorD || (d == mejorD && mejor != null && t.id < mejor.id)) {   // empate: gana el id menor
                    mejorD = d;
                    mejor = t;
                }
            }
        }
        return mejor;
    }

    /** Lo mismo sin índice, para comparar (fuerza bruta, O(n)). */
    public Tramo masCercanoFuerzaBruta(double lat, double lon, Proyeccion p, double maxMetros) {
        comparacionesUltimaBusqueda = 0;
        double[] xy = p.aMetros(lat, lon);
        Tramo mejor = null;
        double mejorD = maxMetros;
        for (Tramo t : todos) {
            comparacionesUltimaBusqueda++;
            double d = distanciaAPolilinea(xy[0], xy[1], t);
            if (d < mejorD || (d == mejorD && mejor != null && t.id < mejor.id)) {
                mejorD = d;
                mejor = t;
            }
        }
        return mejor;
    }

    public long comparacionesUltimaBusqueda() {
        return comparacionesUltimaBusqueda;
    }

    public int numCeldas() {
        return celdas.tamano();
    }

    public TablaHash<String, List<Tramo>> tabla() {
        return celdas;
    }

    /** Distancia (m) de un punto a la polilínea del tramo, en coordenadas proyectadas. */
    public static double distanciaAPolilinea(double px, double py, Tramo t) {
        double mejor = Double.MAX_VALUE;
        for (int i = 0; i + 1 < t.xs.length; i++) {
            double ax = t.xs[i], ay = t.ys[i], bx = t.xs[i + 1], by = t.ys[i + 1];
            double dx = bx - ax, dy = by - ay;
            double largo2 = dx * dx + dy * dy;
            double u = largo2 == 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / largo2));
            double cx = ax + u * dx - px, cy = ay + u * dy - py;
            mejor = Math.min(mejor, Math.sqrt(cx * cx + cy * cy));
        }
        return mejor;
    }
}
