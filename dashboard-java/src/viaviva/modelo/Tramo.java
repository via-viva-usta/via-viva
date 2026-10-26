package viaviva.modelo;

/**
 * Un tramo de calle de OpenStreetMap (tabla tramos) con su riesgo de la corrida elegida.
 * La geometría se guarda en grados y también proyectada a metros para dibujar y medir distancias.
 */
public class Tramo {

    public final int id;
    public final long osmU;
    public final long osmV;
    public final String nombre;
    public final String tipoVia;
    public final double longitudM;
    public final double latCentro;
    public final double lonCentro;
    public final String barrio;
    public final double[] lats;
    public final double[] lons;

    /** Coordenadas en metros (proyección local equirectangular); las llena Proyeccion. */
    public double[] xs;
    public double[] ys;

    /** Probabilidad de la corrida elegida; NaN si no hay riesgo calculado. */
    public double riesgo = Double.NaN;
    /** 1 si el tramo ya tenía huecos conocidos (reportado). */
    public boolean reportado;

    public Tramo(int id, long osmU, long osmV, String nombre, String tipoVia, double longitudM,
                 double latCentro, double lonCentro, String barrio, double[] lats, double[] lons) {
        this.id = id;
        this.osmU = osmU;
        this.osmV = osmV;
        this.nombre = nombre;
        this.tipoVia = tipoVia;
        this.longitudM = longitudM;
        this.latCentro = latCentro;
        this.lonCentro = lonCentro;
        this.barrio = barrio;
        this.lats = lats;
        this.lons = lons;
    }

    public boolean tieneRiesgo() {
        return !Double.isNaN(riesgo);
    }

    public String nombreVisible() {
        // OSM separa con ';' las vías que tienen dos nombres
        return nombre != null && !nombre.isBlank() ? nombre.replace(";", " / ") : "(sin nombre, " + tipoVia + ")";
    }

    @Override
    public String toString() {
        return "Tramo " + id + " · " + nombreVisible();
    }
}
