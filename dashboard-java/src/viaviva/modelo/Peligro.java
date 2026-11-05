package viaviva.modelo;

/**
 * Un peligro en la vía: un reporte ciudadano (tabla reportes, del bot) o un evento detectado
 * (tabla eventos, del nodo o de un recorrido con phyphox). El tablero los lista juntos, ordenados
 * por prioridad = severidad × tránsito × reincidencia (ver {@code control.PrioridadPeligros}).
 */
public class Peligro {

    public enum Fuente {
        REPORTE("Reporte"), EVENTO("Evento");

        private final String texto;

        Fuente(String texto) {
            this.texto = texto;
        }

        @Override
        public String toString() {
            return texto;
        }
    }

    public final Fuente fuente;
    /** id_reporte o id_evento. */
    public final int id;
    /** tipo del reporte o clase del evento: hueco, resalto, obstaculo, ... */
    public final String clase;
    /** eventos.severidad (0–1); null si no viene (los reportes no tienen esa columna). */
    public final Double severidad01;
    /** estado del reporte (nuevo, confirmado, ...); null en los eventos. */
    public final String estado;
    /** Hora UTC en ISO 8601, como está en la base. */
    public final String tsUtc;
    public final double lat;
    public final double lon;
    /** id_tramo que trae la base; null si no lo tiene (el bot no lo llena). */
    public final Integer idTramoBase;
    /** Ruta de la foto tal como está en la base (relativa a via-viva/ o absoluta); null si no hay. */
    public final String fotoRuta;
    /** Origen del dato: telegram/web/sms (reportes) o nodo/phyphox/simulado (eventos). */
    public final String origen;
    /** true si es un dato de prueba (evento simulado, o marcado DEMO): nunca es un resultado. */
    public final boolean demo;

    // ---- se llenan al calcular la prioridad ----
    /** Tramo final: el de la base o el más cercano según el índice geohash; null si no hay ninguno cerca. */
    public Tramo tramo;
    /** true si el tramo lo asignó el tablero con el índice geohash (no venía en la base). */
    public boolean tramoPorIndice;
    /** Severidad normalizada: 1 = leve, 2 = media, 3 = alta. */
    public int nivelSeveridad;
    /** Peso del tránsito por tipo de vía del tramo: 1, 2 o 3. */
    public int pesoTransito;
    /** 1 + otros peligros abiertos en el mismo tramo. */
    public int reincidencia;
    /** severidad × tránsito × reincidencia; 0 si el reporte está cerrado (reparado o descartado). */
    public int prioridad;

    public Peligro(Fuente fuente, int id, String clase, Double severidad01, String estado, String tsUtc,
                   double lat, double lon, Integer idTramoBase, String fotoRuta, String origen, boolean demo) {
        this.fuente = fuente;
        this.id = id;
        this.clase = clase;
        this.severidad01 = severidad01;
        this.estado = estado;
        this.tsUtc = tsUtc;
        this.lat = lat;
        this.lon = lon;
        this.idTramoBase = idTramoBase;
        this.fotoRuta = fotoRuta;
        this.origen = origen;
        this.demo = demo;
    }

    /** Un reporte reparado o descartado ya no es un peligro pendiente. */
    public boolean cerrado() {
        return "reparado".equals(estado) || "descartado".equals(estado);
    }

    public boolean tieneFoto() {
        return fotoRuta != null && !fotoRuta.isBlank();
    }

    /** "2026-10-26T14:05:00Z" → "2026-10-26 14:05". */
    public String fechaCorta() {
        if (tsUtc == null) return "—";
        String s = tsUtc.replace('T', ' ').replace("Z", "");
        return s.length() >= 16 ? s.substring(0, 16) : s;
    }

    @Override
    public String toString() {
        return fuente + " " + id + " · " + clase + (demo ? " [DEMO]" : "");
    }
}
