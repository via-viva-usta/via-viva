package viaviva.modelo;

/**
 * Proyección equirectangular local: grados → metros alrededor de un punto de referencia.
 * Para el tamaño de Tunja (~30 km) el error es despreciable para dibujar y medir distancias cortas.
 */
public class Proyeccion {

    private static final double METROS_POR_GRADO_LAT = 110_574.0;
    private static final double METROS_POR_GRADO_LON_ECUADOR = 111_320.0;

    private final double lat0;
    private final double lon0;
    private final double cosLat0;

    public Proyeccion(double lat0, double lon0) {
        this.lat0 = lat0;
        this.lon0 = lon0;
        this.cosLat0 = Math.cos(Math.toRadians(lat0));
    }

    public double[] aMetros(double lat, double lon) {
        return new double[]{(lon - lon0) * METROS_POR_GRADO_LON_ECUADOR * cosLat0, (lat - lat0) * METROS_POR_GRADO_LAT};
    }

    public double[] aGrados(double x, double y) {
        return new double[]{lat0 + y / METROS_POR_GRADO_LAT, lon0 + x / (METROS_POR_GRADO_LON_ECUADOR * cosLat0)};
    }

    public void proyectar(Tramo t) {
        t.xs = new double[t.lats.length];
        t.ys = new double[t.lats.length];
        for (int i = 0; i < t.lats.length; i++) {
            double[] xy = aMetros(t.lats[i], t.lons[i]);
            t.xs[i] = xy[0];
            t.ys[i] = xy[1];
        }
    }
}
