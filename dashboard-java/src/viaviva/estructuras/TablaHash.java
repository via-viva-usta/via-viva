package viaviva.estructuras;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/**
 * Tabla hash con encadenamiento separado, escrita a mano para el curso de Estructuras de Datos.
 *
 * <p>Capacidad en potencias de 2: el índice es {@code hash & (capacidad - 1)}. Cuando el factor de carga
 * supera 0,75 se duplica la capacidad y se reubican todas las entradas (rehash).</p>
 *
 * <p>Complejidad: insertar, buscar y borrar son O(1) en promedio (cadenas cortas) y O(n) en el peor caso
 * (todas las llaves en la misma cubeta). El rehash cuesta O(n) pero ocurre cada vez que n se duplica,
 * así que el costo amortizado de insertar sigue siendo O(1).</p>
 */
public class TablaHash<K, V> {

    private static final class Entrada<K, V> {
        final K llave;
        V valor;
        Entrada<K, V> siguiente;

        Entrada(K llave, V valor, Entrada<K, V> siguiente) {
            this.llave = llave;
            this.valor = valor;
            this.siguiente = siguiente;
        }
    }

    private static final double CARGA_MAXIMA = 0.75;
    private Entrada<K, V>[] cubetas;
    private int tamano;
    private long colisiones;   // inserciones que cayeron en una cubeta ya ocupada (para el informe)

    public TablaHash() {
        this(16);
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    public TablaHash(int capacidadInicial) {
        int c = 1;
        while (c < capacidadInicial) c <<= 1;
        cubetas = (Entrada<K, V>[]) new Entrada[c];
    }

    private int indice(Object llave, int capacidad) {
        int h = Objects.hashCode(llave);
        h ^= (h >>> 16);              // mezcla los bits altos en los bajos
        return h & (capacidad - 1);
    }

    /** Inserta o reemplaza. Devuelve el valor anterior o null. */
    public V poner(K llave, V valor) {
        int i = indice(llave, cubetas.length);
        for (Entrada<K, V> e = cubetas[i]; e != null; e = e.siguiente) {
            if (Objects.equals(e.llave, llave)) {
                V viejo = e.valor;
                e.valor = valor;
                return viejo;
            }
        }
        if (cubetas[i] != null) colisiones++;
        cubetas[i] = new Entrada<>(llave, valor, cubetas[i]);
        tamano++;
        if (tamano > CARGA_MAXIMA * cubetas.length) redimensionar();
        return null;
    }

    public V obtener(K llave) {
        for (Entrada<K, V> e = cubetas[indice(llave, cubetas.length)]; e != null; e = e.siguiente) {
            if (Objects.equals(e.llave, llave)) return e.valor;
        }
        return null;
    }

    public V obtenerOPorDefecto(K llave, V porDefecto) {
        V v = obtener(llave);
        return v != null ? v : porDefecto;
    }

    public boolean contiene(K llave) {
        for (Entrada<K, V> e = cubetas[indice(llave, cubetas.length)]; e != null; e = e.siguiente) {
            if (Objects.equals(e.llave, llave)) return true;
        }
        return false;
    }

    public V quitar(K llave) {
        int i = indice(llave, cubetas.length);
        Entrada<K, V> previa = null;
        for (Entrada<K, V> e = cubetas[i]; e != null; previa = e, e = e.siguiente) {
            if (Objects.equals(e.llave, llave)) {
                if (previa == null) cubetas[i] = e.siguiente;
                else previa.siguiente = e.siguiente;
                tamano--;
                return e.valor;
            }
        }
        return null;
    }

    @SuppressWarnings({"unchecked", "rawtypes"})
    private void redimensionar() {
        Entrada<K, V>[] viejas = cubetas;
        cubetas = (Entrada<K, V>[]) new Entrada[viejas.length * 2];
        for (Entrada<K, V> cabeza : viejas) {
            for (Entrada<K, V> e = cabeza; e != null; ) {
                Entrada<K, V> sig = e.siguiente;
                int i = indice(e.llave, cubetas.length);
                e.siguiente = cubetas[i];
                cubetas[i] = e;
                e = sig;
            }
        }
    }

    /** Llaves en orden de cubeta (no ordenadas). O(n + capacidad). */
    public List<K> llaves() {
        List<K> lista = new ArrayList<>(tamano);
        for (Entrada<K, V> cabeza : cubetas) {
            for (Entrada<K, V> e = cabeza; e != null; e = e.siguiente) lista.add(e.llave);
        }
        return lista;
    }

    public List<V> valores() {
        List<V> lista = new ArrayList<>(tamano);
        for (Entrada<K, V> cabeza : cubetas) {
            for (Entrada<K, V> e = cabeza; e != null; e = e.siguiente) lista.add(e.valor);
        }
        return lista;
    }

    public int tamano() {
        return tamano;
    }

    public int capacidad() {
        return cubetas.length;
    }

    public long colisiones() {
        return colisiones;
    }

    /** Longitud de la cadena más larga: muestra qué tan bien reparte la función hash. */
    public int cadenaMasLarga() {
        int max = 0;
        for (Entrada<K, V> cabeza : cubetas) {
            int n = 0;
            for (Entrada<K, V> e = cabeza; e != null; e = e.siguiente) n++;
            max = Math.max(max, n);
        }
        return max;
    }
}
