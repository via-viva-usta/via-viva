package viaviva.datos;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import viaviva.estructuras.TablaHash;
import viaviva.modelo.Corrida;
import viaviva.modelo.Peligro;
import viaviva.modelo.Tramo;

/** Lectura de la base SQLite que llena el ETL (db/schema.sql). Solo lectura. */
public class RepositorioSQLite implements AutoCloseable {

    private final Connection con;

    public RepositorioSQLite(String rutaDb) throws SQLException {
        // mode=ro: el tablero nunca modifica la base
        con = DriverManager.getConnection("jdbc:sqlite:file:" + rutaDb.replace('\\', '/') + "?mode=ro");
    }

    public List<Tramo> leerTramos() throws SQLException {
        List<Tramo> lista = new ArrayList<>();
        String sql = "SELECT id_tramo, osm_u, osm_v, nombre, tipo_via, longitud_m, lat_centro, lon_centro, barrio, "
                + "geometria_wkt FROM tramos ORDER BY id_tramo";
        try (Statement st = con.createStatement(); ResultSet rs = st.executeQuery(sql)) {
            while (rs.next()) {
                double[][] geom = leerLineString(rs.getString("geometria_wkt"));
                lista.add(new Tramo(rs.getInt("id_tramo"), rs.getLong("osm_u"), rs.getLong("osm_v"),
                        rs.getString("nombre"), rs.getString("tipo_via"), rs.getDouble("longitud_m"),
                        rs.getDouble("lat_centro"), rs.getDouble("lon_centro"), rs.getString("barrio"),
                        geom[0], geom[1]));
            }
        }
        return lista;
    }

    /** Corridas disponibles en la tabla riesgo, la más reciente primero. */
    public List<Corrida> listarCorridas() throws SQLException {
        List<Corrida> lista = new ArrayList<>();
        String sql = "SELECT modelo, version_modelo, fecha_calculo, COUNT(*) FROM riesgo "
                + "GROUP BY modelo, version_modelo, fecha_calculo ORDER BY fecha_calculo DESC, modelo";
        try (Statement st = con.createStatement(); ResultSet rs = st.executeQuery(sql)) {
            while (rs.next()) {
                lista.add(new Corrida(rs.getString(1), rs.getString(2), rs.getString(3), rs.getInt(4)));
            }
        }
        return lista;
    }

    /** Asigna a cada tramo el riesgo de la corrida (los que no aparecen quedan en NaN). */
    public int aplicarRiesgo(Corrida c, TablaHash<Integer, Tramo> porId) throws SQLException {
        for (Tramo t : porId.valores()) {
            t.riesgo = Double.NaN;
            t.reportado = false;
        }
        String sql = "SELECT id_tramo, probabilidad, reportado FROM riesgo "
                + "WHERE modelo = ? AND version_modelo = ? AND fecha_calculo = ?";
        int n = 0;
        try (PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setString(1, c.modelo());
            ps.setString(2, c.version());
            ps.setString(3, c.fecha());
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    Tramo t = porId.obtener(rs.getInt(1));
                    if (t != null) {
                        t.riesgo = rs.getDouble(2);
                        t.reportado = rs.getInt(3) == 1;
                        n++;
                    }
                }
            }
        }
        return n;
    }

    /** Clases de eventos que son daño u obstáculo de la vía (las mismas que publica web/exportar.py). */
    public static final String CLASES_VIA_SQL = "('hueco', 'resalto', 'impacto_fuerte', 'obstaculo')";

    /** Reportes ciudadanos (bot). DEMO si hash_usuario o descripcion dicen "demo". Vacío si la tabla no existe. */
    public List<Peligro> leerReportes() throws SQLException {
        List<Peligro> lista = new ArrayList<>();
        if (!existeTabla("reportes")) return lista;
        String sql = "SELECT id_reporte, canal, hash_usuario, ts_utc, lat, lon, tipo, descripcion, foto_ruta, estado, "
                + "id_tramo FROM reportes ORDER BY id_reporte";
        try (Statement st = con.createStatement(); ResultSet rs = st.executeQuery(sql)) {
            while (rs.next()) {
                boolean demo = contieneDemo(rs.getString("hash_usuario")) || contieneDemo(rs.getString("descripcion"));
                lista.add(new Peligro(Peligro.Fuente.REPORTE, rs.getInt("id_reporte"), rs.getString("tipo"), null,
                        rs.getString("estado"), rs.getString("ts_utc"), rs.getDouble("lat"), rs.getDouble("lon"),
                        enteroONull(rs, "id_tramo"), rs.getString("foto_ruta"), rs.getString("canal"), demo));
            }
        }
        return lista;
    }

    /**
     * Eventos de la vía (hueco, resalto, impacto fuerte, obstáculo) del nodo o de phyphox. Las maniobras y 'normal'
     * no son peligros de la vía y no se leen. DEMO si origen = 'simulado' o el nodo o el modelo dicen "demo".
     */
    public List<Peligro> leerEventos() throws SQLException {
        List<Peligro> lista = new ArrayList<>();
        if (!existeTabla("eventos")) return lista;
        String sql = "SELECT id_evento, id_nodo, ts_utc, lat, lon, clase, severidad, origen, foto_ruta, modelo_version, "
                + "id_tramo FROM eventos WHERE clase IN " + CLASES_VIA_SQL + " ORDER BY id_evento";
        try (Statement st = con.createStatement(); ResultSet rs = st.executeQuery(sql)) {
            while (rs.next()) {
                String origen = rs.getString("origen");
                boolean demo = "simulado".equals(origen) || contieneDemo(rs.getString("id_nodo"))
                        || contieneDemo(rs.getString("modelo_version"));
                double sev = rs.getDouble("severidad");
                Double severidad = rs.wasNull() ? null : sev;
                lista.add(new Peligro(Peligro.Fuente.EVENTO, rs.getInt("id_evento"), rs.getString("clase"), severidad,
                        null, rs.getString("ts_utc"), rs.getDouble("lat"), rs.getDouble("lon"),
                        enteroONull(rs, "id_tramo"), rs.getString("foto_ruta"), origen, demo));
            }
        }
        return lista;
    }

    /** Eventos que no son de la vía (maniobras y 'normal'): solo se cuentan para avisarlo en el panel. */
    public int contarEventosNoVia() throws SQLException {
        if (!existeTabla("eventos")) return 0;
        try (Statement st = con.createStatement();
             ResultSet rs = st.executeQuery("SELECT COUNT(*) FROM eventos WHERE clase NOT IN " + CLASES_VIA_SQL)) {
            return rs.next() ? rs.getInt(1) : 0;
        }
    }

    private boolean existeTabla(String nombre) throws SQLException {
        try (PreparedStatement ps = con.prepareStatement(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?")) {
            ps.setString(1, nombre);
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next();
            }
        }
    }

    private static Integer enteroONull(ResultSet rs, String columna) throws SQLException {
        int v = rs.getInt(columna);
        return rs.wasNull() ? null : v;
    }

    private static boolean contieneDemo(String s) {
        return s != null && s.toUpperCase().contains("DEMO");
    }

    /** "LINESTRING (lon lat, lon lat, ...)" → {lats, lons}. */
    static double[][] leerLineString(String wkt) {
        int a = wkt.indexOf('('), b = wkt.lastIndexOf(')');
        String[] pares = wkt.substring(a + 1, b).split(",");
        double[] lats = new double[pares.length], lons = new double[pares.length];
        for (int i = 0; i < pares.length; i++) {
            String[] xy = pares[i].trim().split("\\s+");
            lons[i] = Double.parseDouble(xy[0]);
            lats[i] = Double.parseDouble(xy[1]);
        }
        return new double[][]{lats, lons};
    }

    @Override
    public void close() throws SQLException {
        con.close();
    }
}
