package viaviva.estructuras;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import viaviva.modelo.Tramo;

/**
 * Grafo no dirigido de calles: vértices = intersecciones (id OSM), aristas = tramos.
 * Representación: lista de adyacencia guardada en la {@link TablaHash} propia (id de nodo → aristas).
 *
 * <p>Memoria O(V + E). Recorridos en anchura (BFS) en O(V + E).</p>
 */
public class GrafoCalles {

    /** Arista de la lista de adyacencia: a qué nodo lleva y por qué tramo. */
    public record Arista(long destino, Tramo tramo) {
    }

    /** Resultado de un BFS: tramos alcanzados y a cuántas intersecciones del origen quedó cada uno. */
    public record ResultadoBFS(List<Tramo> tramos, List<Integer> saltos, int nodosVisitados) {
    }

    private final TablaHash<Long, List<Arista>> adyacencia = new TablaHash<>(8192);
    private int aristas;

    public void agregarTramo(Tramo t) {
        listaDe(t.osmU).add(new Arista(t.osmV, t));
        listaDe(t.osmV).add(new Arista(t.osmU, t));
        aristas++;
    }

    private List<Arista> listaDe(long nodo) {
        List<Arista> l = adyacencia.obtener(nodo);
        if (l == null) {
            l = new ArrayList<>(4);
            adyacencia.poner(nodo, l);
        }
        return l;
    }

    public List<Arista> vecinos(long nodo) {
        return adyacencia.obtenerOPorDefecto(nodo, List.of());
    }

    public int numNodos() {
        return adyacencia.tamano();
    }

    public int numAristas() {
        return aristas;
    }

    public TablaHash<Long, List<Arista>> tablaAdyacencia() {
        return adyacencia;
    }

    /**
     * BFS desde los dos extremos de un tramo hasta {@code maxSaltos} intersecciones de distancia.
     * Sirve para ver el "corredor" de un tramo: qué calles comparten la misma zona de trabajo.
     * Costo: O(V' + E'), donde V' y E' son los nodos y tramos dentro del radio.
     */
    public ResultadoBFS corredor(Tramo origen, int maxSaltos) {
        TablaHash<Long, Integer> distancia = new TablaHash<>();
        TablaHash<Integer, Boolean> tramoVisto = new TablaHash<>();
        ArrayDeque<Long> cola = new ArrayDeque<>();
        List<Tramo> tramos = new ArrayList<>();
        List<Integer> saltos = new ArrayList<>();

        tramos.add(origen);
        saltos.add(0);
        tramoVisto.poner(origen.id, true);
        for (long extremo : new long[]{origen.osmU, origen.osmV}) {
            if (!distancia.contiene(extremo)) {
                distancia.poner(extremo, 0);
                cola.add(extremo);
            }
        }
        while (!cola.isEmpty()) {
            long n = cola.poll();
            int d = distancia.obtener(n);
            if (d >= maxSaltos) continue;
            for (Arista a : vecinos(n)) {
                if (!tramoVisto.contiene(a.tramo().id)) {
                    tramoVisto.poner(a.tramo().id, true);
                    tramos.add(a.tramo());
                    saltos.add(d + 1);
                }
                if (!distancia.contiene(a.destino())) {
                    distancia.poner(a.destino(), d + 1);
                    cola.add(a.destino());
                }
            }
        }
        return new ResultadoBFS(tramos, saltos, distancia.tamano());
    }

    /**
     * Zonas de alto riesgo: componentes conexas del subgrafo formado SOLO por tramos con riesgo ≥ umbral.
     * Cada zona es un grupo de calles de alto riesgo pegadas entre sí: una orden de trabajo candidata.
     * Se encuentran con un BFS por componente; en total O(V + E).
     * Devuelve las zonas ordenadas por longitud total (m), de mayor a menor.
     */
    public List<List<Tramo>> zonasDeRiesgo(double umbral) {
        TablaHash<Long, Boolean> visitado = new TablaHash<>(8192);
        List<List<Tramo>> zonas = new ArrayList<>();
        for (Long inicio : adyacencia.llaves()) {
            if (visitado.contiene(inicio) || !tocaTramoRiesgoso(inicio, umbral)) continue;
            List<Tramo> zona = new ArrayList<>();
            TablaHash<Integer, Boolean> tramoVisto = new TablaHash<>();
            ArrayDeque<Long> cola = new ArrayDeque<>();
            cola.add(inicio);
            visitado.poner(inicio, true);
            while (!cola.isEmpty()) {
                long n = cola.poll();
                for (Arista a : vecinos(n)) {
                    if (!a.tramo().tieneRiesgo() || a.tramo().riesgo < umbral) continue;
                    if (!tramoVisto.contiene(a.tramo().id)) {
                        tramoVisto.poner(a.tramo().id, true);
                        zona.add(a.tramo());
                    }
                    if (!visitado.contiene(a.destino())) {
                        visitado.poner(a.destino(), true);
                        cola.add(a.destino());
                    }
                }
            }
            zonas.add(zona);
        }
        zonas.sort(Comparator.comparingDouble(GrafoCalles::longitudTotal).reversed());
        return zonas;
    }

    private boolean tocaTramoRiesgoso(long nodo, double umbral) {
        for (Arista a : vecinos(nodo)) {
            if (a.tramo().tieneRiesgo() && a.tramo().riesgo >= umbral) return true;
        }
        return false;
    }

    public static double longitudTotal(List<Tramo> tramos) {
        double s = 0;
        for (Tramo t : tramos) s += t.longitudM;
        return s;
    }
}
