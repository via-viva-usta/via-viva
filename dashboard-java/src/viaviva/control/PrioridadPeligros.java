package viaviva.control;

import java.util.Comparator;
import java.util.List;
import viaviva.estructuras.MonticuloMax;
import viaviva.estructuras.TablaHash;
import viaviva.modelo.Peligro;

/**
 * Prioridad de atención de reportes y eventos: <b>prioridad = severidad × tránsito × reincidencia</b>.
 *
 * <ul>
 *   <li><b>Severidad</b> (1 leve, 2 media, 3 alta). Eventos con {@code severidad} (0–1): &lt; 1/3 → 1,
 *       &lt; 2/3 → 2, si no 3. Si no hay número (los reportes no tienen esa columna; los eventos de phyphox
 *       la dejan vacía), se usa la clase: hueco e impacto_fuerte → 3; obstaculo y otro → 2;
 *       resalto y vehiculo_varado → 1 (el resalto es parte de la vía; el vehículo varado es transitorio).</li>
 *   <li><b>Tránsito</b> por {@code tipo_via} del tramo (OSM): trunk/primary (y sus _link) → 3;
 *       secondary/tertiary (y _link) → 2; residential, unclassified y otros → 1. Si el tipo trae varios
 *       valores separados por ';' se toma el mayor. Sin tramo → 1.</li>
 *   <li><b>Reincidencia</b> = 1 + los otros peligros abiertos en el mismo tramo (es decir, cuántos hay en ese
 *       tramo contándose a sí mismo). Se cuenta con una {@link TablaHash} tramo → cantidad. Lo DEMO se cuenta
 *       aparte de lo real (no infla la prioridad de un dato real). Sin tramo → 1.</li>
 *   <li>Un reporte cerrado (reparado o descartado) queda con prioridad 0, no cuenta para la reincidencia
 *       y sale al final de la lista.</li>
 * </ul>
 * Empates: mayor severidad, luego la fecha más reciente, luego reportes antes que eventos y el id menor.
 */
public final class PrioridadPeligros {

    private PrioridadPeligros() {
    }

    /** Severidad normalizada a 1–3 (regla en la documentación de la clase). */
    public static int nivelSeveridad(Double severidad01, String clase) {
        if (severidad01 != null && !severidad01.isNaN()) {
            double s = Math.max(0, Math.min(1, severidad01));
            return s < 1.0 / 3 ? 1 : s < 2.0 / 3 ? 2 : 3;
        }
        if (clase == null) return 2;
        return switch (clase) {
            case "hueco", "impacto_fuerte" -> 3;
            case "resalto", "vehiculo_varado" -> 1;
            default -> 2;                       // obstaculo, otro, o una clase nueva sin regla
        };
    }

    /** Peso del tránsito según el tipo de vía de OSM. */
    public static int pesoTransito(String tipoVia) {
        if (tipoVia == null || tipoVia.isBlank()) return 1;
        int mejor = 1;
        for (String parte : tipoVia.split(";")) {
            String t = parte.trim().toLowerCase();
            if (t.endsWith("_link")) t = t.substring(0, t.length() - 5);
            int p = switch (t) {
                case "motorway", "trunk", "primary" -> 3;
                case "secondary", "tertiary" -> 2;
                default -> 1;
            };
            mejor = Math.max(mejor, p);
        }
        return mejor;
    }

    /** Llave del conteo por tramo: lo DEMO y lo real en grupos distintos. */
    private static long llaveTramo(Peligro p) {
        return p.tramo.id * 2L + (p.demo ? 1 : 0);
    }

    /**
     * Llena severidad, tránsito, reincidencia y prioridad de cada peligro (los tramos ya deben estar asignados).
     * Dos pasadas O(n): contar por tramo en la tabla hash y luego multiplicar. Devuelve la tabla del conteo.
     */
    public static TablaHash<Long, Integer> calcular(List<Peligro> peligros) {
        TablaHash<Long, Integer> porTramo = new TablaHash<>(Math.max(16, peligros.size() * 2));
        for (Peligro p : peligros) {
            if (p.tramo == null || p.cerrado()) continue;
            long k = llaveTramo(p);
            porTramo.poner(k, porTramo.obtenerOPorDefecto(k, 0) + 1);   // O(1) promedio
        }
        for (Peligro p : peligros) {
            p.nivelSeveridad = nivelSeveridad(p.severidad01, p.clase);
            p.pesoTransito = p.tramo == null ? 1 : pesoTransito(p.tramo.tipoVia);
            p.reincidencia = (p.tramo == null || p.cerrado()) ? 1 : porTramo.obtener(llaveTramo(p));
            p.prioridad = p.cerrado() ? 0 : p.nivelSeveridad * p.pesoTransito * p.reincidencia;
        }
        return porTramo;
    }

    /** Orden de atención (mayor primero) con los desempates de la documentación. */
    public static final Comparator<Peligro> ORDEN = Comparator
            .comparingInt((Peligro p) -> p.prioridad)
            .thenComparingInt(p -> p.nivelSeveridad)
            .thenComparing(p -> p.tsUtc == null ? "" : p.tsUtc)            // ISO 8601: el orden de texto es el de fecha
            .thenComparing(p -> p.fuente == Peligro.Fuente.REPORTE ? 1 : 0)
            .thenComparing(p -> -p.id);

    /** Los k de mayor prioridad con el montículo: construir O(n) + extraer O(k log n). */
    public static List<Peligro> topK(List<Peligro> peligros, int k) {
        MonticuloMax<Peligro> heap = new MonticuloMax<>(peligros, ORDEN);
        return heap.extraerK(k);
    }
}
