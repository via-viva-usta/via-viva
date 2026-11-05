package viaviva.herramientas;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import viaviva.control.PrioridadPeligros;
import viaviva.modelo.Peligro;
import viaviva.modelo.Tramo;

/**
 * Prueba de la prioridad de reportes y eventos (severidad × tránsito × reincidencia) con datos de ejemplo EN MEMORIA
 * (inventados para la prueba, no son datos de Tunja). No necesita la base.
 * En NetBeans: clic derecho → Run File. Por consola:
 * <pre>java -cp build/classes;lib/* viaviva.herramientas.PruebaPrioridad</pre>
 * PruebaEstructuras también la corre.
 */
public class PruebaPrioridad {

    private static int fallas;

    public static void main(String[] args) {
        Locale.setDefault(Locale.ROOT);
        int f = correr();
        System.out.println(f == 0 ? "\nTODAS LAS PRUEBAS DE PRIORIDAD PASARON" : "\n" + f + " PRUEBA(S) FALLARON");
        System.exit(f == 0 ? 0 : 1);
    }

    /** Corre todas las verificaciones y devuelve cuántas fallaron. */
    public static int correr() {
        fallas = 0;
        System.out.println("== Prueba de la prioridad de reportes y eventos (datos de ejemplo en memoria) ==");
        probarSeveridad();
        probarTransito();
        probarOrden();
        probarVacio();
        return fallas;
    }

    private static void verificar(boolean ok, String que) {
        System.out.println((ok ? "  OK     " : "  FALLA  ") + que);
        if (!ok) fallas++;
    }

    private static void probarSeveridad() {
        verificar(PrioridadPeligros.nivelSeveridad(0.10, "hueco") == 1
                && PrioridadPeligros.nivelSeveridad(1.0 / 3, "hueco") == 2
                && PrioridadPeligros.nivelSeveridad(0.50, "hueco") == 2
                && PrioridadPeligros.nivelSeveridad(0.90, "resalto") == 3,
                "Severidad 0–1 → 1/2/3 por tercios (el número manda sobre la clase)");
        verificar(PrioridadPeligros.nivelSeveridad(null, "hueco") == 3
                && PrioridadPeligros.nivelSeveridad(null, "impacto_fuerte") == 3
                && PrioridadPeligros.nivelSeveridad(null, "obstaculo") == 2
                && PrioridadPeligros.nivelSeveridad(null, "otro") == 2
                && PrioridadPeligros.nivelSeveridad(null, "resalto") == 1
                && PrioridadPeligros.nivelSeveridad(null, "vehiculo_varado") == 1,
                "Severidad sin número → por clase (hueco 3, obstáculo 2, resalto 1, ...)");
    }

    private static void probarTransito() {
        verificar(PrioridadPeligros.pesoTransito("trunk") == 3 && PrioridadPeligros.pesoTransito("primary") == 3
                && PrioridadPeligros.pesoTransito("trunk_link") == 3
                && PrioridadPeligros.pesoTransito("secondary") == 2 && PrioridadPeligros.pesoTransito("tertiary") == 2
                && PrioridadPeligros.pesoTransito("residential") == 1
                && PrioridadPeligros.pesoTransito("unclassified") == 1 && PrioridadPeligros.pesoTransito(null) == 1,
                "Tránsito por tipo de vía: trunk/primary 3, secondary/tertiary 2, residential/otros 1");
        verificar(PrioridadPeligros.pesoTransito("unclassified;tertiary") == 2,
                "Tipo de vía con varios valores (';') → el mayor");
    }

    private static Tramo tramo(int id, String tipoVia) {
        return new Tramo(id, id, id + 1000, "calle " + id, tipoVia, 100, 5.53, -73.36, null,
                new double[]{5.53, 5.531}, new double[]{-73.36, -73.361});
    }

    private static Peligro reporte(int id, String tipo, String estado, String ts, Tramo t) {
        Peligro p = new Peligro(Peligro.Fuente.REPORTE, id, tipo, null, estado, ts, 5.53, -73.36,
                t == null ? null : t.id, null, "telegram", false);
        p.tramo = t;
        return p;
    }

    private static Peligro evento(int id, String clase, double sev, String ts, Tramo t, boolean simulado) {
        Peligro p = new Peligro(Peligro.Fuente.EVENTO, id, clase, sev, null, ts, 5.53, -73.36, t.id, null,
                simulado ? "simulado" : "nodo", simulado);
        p.tramo = t;
        return p;
    }

    private static void probarOrden() {
        Tramo a = tramo(1, "primary"), b = tramo(2, "tertiary"), c = tramo(3, "residential");
        List<Peligro> lista = new ArrayList<>();
        Peligro r1 = reporte(1, "hueco", "nuevo", "2026-11-01T10:00:00Z", a);          // 3 × 3 × 2 = 18
        Peligro e1 = evento(1, "resalto", 0.20, "2026-11-01T11:00:00Z", a, false);    // 1 × 3 × 2 = 6
        Peligro r2 = reporte(2, "obstaculo", "confirmado", "2026-11-02T09:00:00Z", b); // 2 × 2 × 1 = 4
        Peligro e2 = evento(2, "hueco", 0.90, "2026-11-02T08:00:00Z", c, false);      // 3 × 1 × 3 = 9
        Peligro e3 = evento(3, "hueco", 0.80, "2026-11-03T08:00:00Z", c, false);      // 9 (más reciente que e2)
        Peligro e4 = evento(4, "hueco", 0.70, "2026-11-04T08:00:00Z", c, false);      // 9 (la más reciente)
        Peligro r3 = reporte(3, "hueco", "reparado", "2026-11-04T12:00:00Z", a);      // cerrado → 0, no cuenta
        Peligro d1 = evento(5, "hueco", 0.95, "2026-10-30T08:00:00Z", a, true);       // DEMO: 3 × 3 × 1 = 9
        Peligro r4 = reporte(4, "hueco", "nuevo", "2026-11-04T13:00:00Z", null);      // sin tramo: 3 × 1 × 1 = 3
        // se insertan desordenados a propósito
        lista.add(r3);
        lista.add(e2);
        lista.add(r4);
        lista.add(d1);
        lista.add(e1);
        lista.add(r2);
        lista.add(e4);
        lista.add(r1);
        lista.add(e3);

        PrioridadPeligros.calcular(lista);
        verificar(r1.prioridad == 18 && r1.reincidencia == 2 && r1.pesoTransito == 3 && r1.nivelSeveridad == 3,
                "Reporte de hueco en vía primaria con otro peligro abierto en el tramo: 3 × 3 × 2 = 18");
        verificar(e2.reincidencia == 3 && e2.prioridad == 9, "Tres eventos en el mismo tramo residencial: 3 × 1 × 3 = 9");
        verificar(r3.prioridad == 0 && r3.reincidencia == 1, "Reporte reparado: prioridad 0 y no cuenta en su tramo");
        verificar(d1.reincidencia == 1 && d1.prioridad == 9, "Lo DEMO se cuenta aparte: no sube la reincidencia real");
        verificar(r4.prioridad == 3 && r4.pesoTransito == 1, "Sin tramo: tránsito 1 y reincidencia 1");

        List<Peligro> orden = PrioridadPeligros.topK(lista, lista.size());
        List<Peligro> esperado = List.of(r1, e4, e3, e2, d1, e1, r2, r4, r3);
        StringBuilder sb = new StringBuilder();
        for (Peligro p : orden) {
            sb.append(p.fuente == Peligro.Fuente.REPORTE ? "R" : "E").append(p.id).append('=').append(p.prioridad)
                    .append(' ');
        }
        System.out.println("         orden del montículo: " + sb.toString().trim());
        verificar(orden.equals(esperado), "Orden completo correcto (empates: severidad, luego la fecha más reciente)");
        verificar(PrioridadPeligros.topK(lista, 3).equals(esperado.subList(0, 3)), "Top-3 con el montículo");

        List<Peligro> ordenado = new ArrayList<>(lista);   // comparación con ordenar todo (solo para verificar)
        ordenado.sort(PrioridadPeligros.ORDEN.reversed());
        verificar(orden.equals(ordenado), "Montículo = ordenar con el mismo criterio");
    }

    private static void probarVacio() {
        List<Peligro> vacia = new ArrayList<>();
        PrioridadPeligros.calcular(vacia);
        verificar(PrioridadPeligros.topK(vacia, 100).isEmpty(), "Sin reportes ni eventos: lista vacía, sin errores");
    }
}
