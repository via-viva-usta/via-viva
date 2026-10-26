package viaviva.control;

import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import viaviva.datos.RepositorioSQLite;
import viaviva.estructuras.GrafoCalles;
import viaviva.estructuras.IndiceGeohash;
import viaviva.estructuras.MonticuloMax;
import viaviva.estructuras.TablaHash;
import viaviva.modelo.Corrida;
import viaviva.modelo.Proyeccion;
import viaviva.modelo.Tramo;

/**
 * Carga la base y arma las estructuras: tabla hash por id, grafo de calles, índice geohash y,
 * en cada consulta, el montículo del ranking. La vista solo llama a estos métodos.
 */
public class ControladorTablero {

    public static final int PRECISION_GEOHASH = 7;   // celdas de ~153 m × 153 m

    private final String rutaDb;
    private List<Tramo> tramos = List.of();
    private final TablaHash<Integer, Tramo> porId = new TablaHash<>(8192);
    private final GrafoCalles grafo = new GrafoCalles();
    private final IndiceGeohash indice = new IndiceGeohash(PRECISION_GEOHASH);
    private Proyeccion proyeccion;
    private List<Corrida> corridas = List.of();
    private Corrida corridaActual;
    private double[] cortesQuintiles = new double[0];
    private long msCarga;

    public ControladorTablero(String rutaDb) {
        this.rutaDb = rutaDb;
    }

    public void cargar() throws SQLException {
        long t0 = System.nanoTime();
        try (RepositorioSQLite repo = new RepositorioSQLite(rutaDb)) {
            tramos = repo.leerTramos();
            corridas = repo.listarCorridas();
        }
        if (tramos.isEmpty()) throw new SQLException("La tabla tramos está vacía: corre python -m etl.osm_tunja");
        double lat0 = tramos.stream().mapToDouble(t -> t.latCentro).average().orElse(5.5353);
        double lon0 = tramos.stream().mapToDouble(t -> t.lonCentro).average().orElse(-73.3678);
        proyeccion = new Proyeccion(lat0, lon0);
        for (Tramo t : tramos) {
            proyeccion.proyectar(t);
            porId.poner(t.id, t);       // tabla hash id → tramo: O(1) promedio por consulta
            grafo.agregarTramo(t);      // lista de adyacencia
            indice.insertar(t);         // tabla hash geohash → tramos
        }
        msCarga = (System.nanoTime() - t0) / 1_000_000;
        if (!corridas.isEmpty()) elegirCorrida(corridaPorDefecto());
    }

    /** La más reciente que no sea demo; si solo hay demos, la más reciente (con preferencia por el bosque). */
    private Corrida corridaPorDefecto() {
        Comparator<Corrida> orden = Comparator.comparing(Corrida::fecha).reversed()
                .thenComparing(c -> c.modelo().equals("bosque") ? 0 : 1);
        return corridas.stream().filter(c -> !c.esDemo()).min(orden)
                .orElse(corridas.stream().min(orden).orElse(null));
    }

    public void elegirCorrida(Corrida c) throws SQLException {
        try (RepositorioSQLite repo = new RepositorioSQLite(rutaDb)) {
            repo.aplicarRiesgo(c, porId);
        }
        corridaActual = c;
        double[] valores = tramos.stream().filter(Tramo::tieneRiesgo).mapToDouble(t -> t.riesgo).sorted().toArray();
        cortesQuintiles = new double[4];
        for (int i = 1; i <= 4 && valores.length > 0; i++) {
            cortesQuintiles[i - 1] = valores[Math.min(valores.length - 1, i * valores.length / 5)];
        }
    }

    /** Clase de color 0..4 (quintiles de la corrida); -1 si el tramo no tiene riesgo. */
    public int claseRiesgo(Tramo t) {
        if (!t.tieneRiesgo() || cortesQuintiles.length == 0) return -1;
        int c = 0;
        while (c < 4 && t.riesgo >= cortesQuintiles[c]) c++;
        return c;
    }

    /** Top-k por riesgo con el montículo: construir O(n) + extraer O(k log n). */
    public List<Tramo> topRiesgo(int k, boolean soloNoReportados) {
        List<Tramo> candidatos = new ArrayList<>();
        for (Tramo t : tramos) {
            if (t.tieneRiesgo() && !(soloNoReportados && t.reportado)) candidatos.add(t);
        }
        MonticuloMax<Tramo> heap = new MonticuloMax<>(candidatos, Comparator.comparingDouble(t -> t.riesgo));
        return heap.extraerK(k);
    }

    /** Valor de riesgo en el percentil p (0-100) de la corrida actual. */
    public double percentilRiesgo(double p) {
        double[] v = tramos.stream().filter(Tramo::tieneRiesgo).mapToDouble(t -> t.riesgo).toArray();
        if (v.length == 0) return Double.NaN;
        Arrays.sort(v);
        return v[(int) Math.min(v.length - 1, Math.floor(p / 100.0 * v.length))];
    }

    public GrafoCalles.ResultadoBFS corredor(Tramo t, int saltos) {
        return grafo.corredor(t, saltos);
    }

    public List<List<Tramo>> zonasDeRiesgo(double umbral) {
        return grafo.zonasDeRiesgo(umbral);
    }

    public Tramo tramoCercano(double x, double y, double maxMetros) {
        double[] ll = proyeccion.aGrados(x, y);
        return indice.masCercano(ll[0], ll[1], proyeccion, maxMetros);
    }

    // ---- acceso para la vista ----
    public List<Tramo> tramos() { return tramos; }
    public GrafoCalles grafo() { return grafo; }
    public IndiceGeohash indice() { return indice; }
    public TablaHash<Integer, Tramo> porId() { return porId; }
    public Proyeccion proyeccion() { return proyeccion; }
    public List<Corrida> corridas() { return corridas; }
    public Corrida corridaActual() { return corridaActual; }
    public double[] cortesQuintiles() { return cortesQuintiles; }
    public long msCarga() { return msCarga; }
    public String rutaDb() { return rutaDb; }
}
