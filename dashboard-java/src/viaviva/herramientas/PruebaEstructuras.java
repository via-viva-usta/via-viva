package viaviva.herramientas;

import java.io.File;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Random;
import viaviva.control.ControladorTablero;
import viaviva.estructuras.GrafoCalles;
import viaviva.estructuras.Geohash;
import viaviva.estructuras.IndiceGeohash;
import viaviva.estructuras.MonticuloMax;
import viaviva.estructuras.TablaHash;
import viaviva.modelo.Proyeccion;
import viaviva.modelo.Tramo;

/**
 * Pruebas de las estructuras propias y mediciones para el informe de Estructuras de Datos.
 * En NetBeans: clic derecho sobre este archivo → Run File. Por consola:
 * <pre>java -cp build/classes;lib/* viaviva.herramientas.PruebaEstructuras [ruta/a/via_viva.db]</pre>
 */
public class PruebaEstructuras {

    private static int fallas = 0;

    public static void main(String[] args) throws Exception {
        Locale.setDefault(Locale.ROOT);
        System.out.println("== Pruebas de estructuras (sin base de datos) ==");
        probarGeohash();
        probarTablaHash();
        probarMonticulo();
        probarBFS();

        String ruta = args.length > 0 ? args[0] : (new File("../data/via_viva.db").isFile() ? "../data/via_viva.db" : null);
        if (ruta != null) {
            System.out.println("\n== Mediciones con la base real: " + new File(ruta).getAbsolutePath() + " ==");
            medirConBase(ruta);
        } else {
            System.out.println("\n(No se encontró via_viva.db: se omiten las mediciones con datos reales.)");
        }
        System.out.println(fallas == 0 ? "\nTODAS LAS PRUEBAS PASARON" : "\n" + fallas + " PRUEBA(S) FALLARON");
        System.exit(fallas == 0 ? 0 : 1);
    }

    private static void verificar(boolean ok, String que) {
        System.out.println((ok ? "  OK     " : "  FALLA  ") + que);
        if (!ok) fallas++;
    }

    private static void probarGeohash() {
        verificar(Geohash.codificar(57.64911, 10.40744, 11).equals("u4pruydqqvj"), "Geohash de referencia (Wikipedia)");
        verificar(Geohash.codificar(5.5353, -73.3678, 7).equals("d2gz6rx"), "Geohash igual al de etl/geohash.py");
        String[] v = Geohash.celdaYVecinas("d2gz6r");
        verificar(v.length == 9 && v[4].equals("d2gz6r"), "Celda central y 8 vecinas");
    }

    private static void probarTablaHash() {
        TablaHash<Integer, Integer> propia = new TablaHash<>();
        Map<Integer, Integer> java = new HashMap<>();
        Random r = new Random(1);
        boolean igual = true;
        for (int i = 0; i < 200_000; i++) {
            int k = r.nextInt(50_000), op = r.nextInt(3);
            if (op == 0) igual &= java.put(k, i) == null ? propia.poner(k, i) == null : propia.poner(k, i) != null;
            else if (op == 1) igual &= eq(java.get(k), propia.obtener(k));
            else igual &= eq(java.remove(k), propia.quitar(k));
        }
        verificar(igual && propia.tamano() == java.size(), "TablaHash = HashMap en 200 000 operaciones al azar");
        System.out.printf("         tamaño %d, capacidad %d, cadena más larga %d%n",
                propia.tamano(), propia.capacidad(), propia.cadenaMasLarga());
    }

    private static boolean eq(Object a, Object b) {
        return a == null ? b == null : a.equals(b);
    }

    private static void probarMonticulo() {
        Random r = new Random(2);
        List<Double> datos = new ArrayList<>();
        for (int i = 0; i < 50_000; i++) datos.add(r.nextDouble());
        MonticuloMax<Double> h = new MonticuloMax<>(datos, Comparator.naturalOrder());
        List<Double> ordenados = new ArrayList<>(datos);
        ordenados.sort(Comparator.reverseOrder());
        verificar(h.extraerK(100).equals(ordenados.subList(0, 100)), "Top-100 del montículo = top-100 ordenando");
        MonticuloMax<Integer> h2 = new MonticuloMax<>(Comparator.naturalOrder());
        for (int i = 0; i < 1000; i++) h2.insertar(r.nextInt(100));
        int anterior = Integer.MAX_VALUE;
        boolean noCrece = true;
        while (!h2.estaVacio()) {
            int x = h2.extraerMax();
            noCrece &= x <= anterior;
            anterior = x;
        }
        verificar(noCrece, "Extraer todo sale en orden no creciente");
    }

    /** Rejilla de 4 × 4 intersecciones: el BFS debe contar las calles por saltos. */
    private static void probarBFS() {
        GrafoCalles g = new GrafoCalles();
        Proyeccion p = new Proyeccion(0, 0);
        int id = 0;
        for (int f = 0; f < 4; f++) {
            for (int c = 0; c < 4; c++) {
                long n = f * 4L + c;
                if (c < 3) agregar(g, p, ++id, n, n + 1);
                if (f < 3) agregar(g, p, ++id, n, n + 4);
            }
        }
        Tramo t0 = null;
        for (GrafoCalles.Arista a : g.vecinos(0)) if (a.destino() == 1) t0 = a.tramo();
        verificar(g.numNodos() == 16 && g.numAristas() == 24, "Rejilla 4×4: 16 nodos y 24 tramos");
        // Desde el tramo 0-1: a 1 salto están los otros tramos que tocan los nodos 0 y 1 (0-4, 1-2, 1-5) → 4 tramos
        verificar(g.corredor(t0, 1).tramos().size() == 4, "BFS a 1 salto desde el tramo 0-1 → 4 tramos");
        verificar(g.corredor(t0, 10).tramos().size() == 24, "BFS sin límite alcanza los 24 tramos");
    }

    private static void agregar(GrafoCalles g, Proyeccion p, int id, long u, long v) {
        Tramo t = new Tramo(id, u, v, "t" + id, "residential", 100, 0, 0, null,
                new double[]{u / 4 * 0.001, v / 4 * 0.001}, new double[]{u % 4 * 0.001, v % 4 * 0.001});
        p.proyectar(t);
        g.agregarTramo(t);
    }

    private static void medirConBase(String ruta) throws Exception {
        ControladorTablero ctl = new ControladorTablero(ruta);
        ctl.cargar();
        List<Tramo> ts = ctl.tramos();
        System.out.printf("  Carga y armado de estructuras: %d ms (%d tramos, %d nodos, %d celdas geohash)%n",
                ctl.msCarga(), ts.size(), ctl.grafo().numNodos(), ctl.indice().numCeldas());
        verificar(ctl.grafo().numAristas() == ts.size(), "El grafo tiene un tramo por arista");

        // Búsqueda del tramo más cercano: índice geohash vs. fuerza bruta, en 2000 puntos sobre las calles
        Random r = new Random(3);
        IndiceGeohash idx = ctl.indice();
        Proyeccion p = ctl.proyeccion();
        long compIdx = 0, compBruta = 0, nsIdx = 0, nsBruta = 0;
        int distintos = 0, n = 2000;
        for (int i = 0; i < n; i++) {
            Tramo t = ts.get(r.nextInt(ts.size()));
            int k = r.nextInt(t.lats.length);
            double lat = t.lats[k] + (r.nextDouble() - 0.5) * 2e-4, lon = t.lons[k] + (r.nextDouble() - 0.5) * 2e-4;
            long a = System.nanoTime();
            Tramo x = idx.masCercano(lat, lon, p, 50);
            nsIdx += System.nanoTime() - a;
            compIdx += idx.comparacionesUltimaBusqueda();
            a = System.nanoTime();
            Tramo y = idx.masCercanoFuerzaBruta(lat, lon, p, 50);
            nsBruta += System.nanoTime() - a;
            compBruta += idx.comparacionesUltimaBusqueda();
            if (x != y) distintos++;
        }
        System.out.printf("  Tramo más cercano (%d búsquedas): geohash %.0f comparaciones y %.1f µs promedio; "
                + "fuerza bruta %.0f comparaciones y %.1f µs%n", n, (double) compIdx / n, nsIdx / 1e3 / n,
                (double) compBruta / n, nsBruta / 1e3 / n);
        verificar(distintos == 0, "Geohash y fuerza bruta encuentran el mismo tramo (" + distintos + " distintos)");

        if (ctl.corridaActual() != null) {
            System.out.println("  Corrida: " + ctl.corridaActual());
            List<Tramo> conRiesgo = ts.stream().filter(Tramo::tieneRiesgo).toList();
            long a = System.nanoTime();
            List<Tramo> topHeap = ctl.topRiesgo(20, false);
            long nsHeap = System.nanoTime() - a;
            a = System.nanoTime();
            List<Tramo> orden = new ArrayList<>(conRiesgo);
            orden.sort(Comparator.comparingDouble((Tramo t) -> t.riesgo).reversed());
            long nsSort = System.nanoTime() - a;
            boolean mismo = true;
            for (int i = 0; i < 20; i++) mismo &= topHeap.get(i).riesgo == orden.get(i).riesgo;
            verificar(mismo, "Top-20 del montículo = top-20 ordenando");
            System.out.printf("         montículo %.2f ms vs. ordenar todo %.2f ms (n = %d)%n",
                    nsHeap / 1e6, nsSort / 1e6, conRiesgo.size());
            double umbral = ctl.percentilRiesgo(90);
            a = System.nanoTime();
            List<List<Tramo>> zonas = ctl.zonasDeRiesgo(umbral);
            System.out.printf("  Zonas de riesgo ≥ p90 (%.3f): %d componentes, la mayor con %d tramos, en %.2f ms%n",
                    umbral, zonas.size(), zonas.isEmpty() ? 0 : zonas.get(0).size(), (System.nanoTime() - a) / 1e6);
            int enZonas = zonas.stream().mapToInt(List::size).sum();
            long sobreUmbral = conRiesgo.stream().filter(t -> t.riesgo >= umbral).count();
            verificar(enZonas == sobreUmbral, "Cada tramo sobre el umbral queda en exactamente una zona");
        }
    }
}
