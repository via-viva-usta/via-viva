package viaviva.estructuras;

import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.List;

/**
 * Montículo binario de máximos (heap) en un arreglo, escrito a mano.
 *
 * <p>El hijo izquierdo de i está en 2i+1 y el derecho en 2i+2; el padre en (i-1)/2.
 * Se usa para el ranking de tramos por riesgo: construir el montículo con los n tramos cuesta O(n)
 * (algoritmo de Floyd) y sacar los k mayores cuesta O(k log n), mejor que ordenar todo, O(n log n),
 * cuando k es mucho menor que n.</p>
 */
public class MonticuloMax<T> {

    private final List<T> datos;
    private final Comparator<? super T> comparador;

    public MonticuloMax(Comparator<? super T> comparador) {
        this.datos = new ArrayList<>();
        this.comparador = comparador;
    }

    /** Construye el montículo de una sola vez en O(n) (heapify de Floyd). */
    public MonticuloMax(Collection<? extends T> elementos, Comparator<? super T> comparador) {
        this.datos = new ArrayList<>(elementos);
        this.comparador = comparador;
        for (int i = datos.size() / 2 - 1; i >= 0; i--) bajar(i);
    }

    /** O(log n). */
    public void insertar(T x) {
        datos.add(x);
        subir(datos.size() - 1);
    }

    /** O(1). */
    public T verMax() {
        return datos.isEmpty() ? null : datos.get(0);
    }

    /** O(log n). */
    public T extraerMax() {
        if (datos.isEmpty()) return null;
        T max = datos.get(0);
        T ultimo = datos.remove(datos.size() - 1);
        if (!datos.isEmpty()) {
            datos.set(0, ultimo);
            bajar(0);
        }
        return max;
    }

    /** Los k mayores en orden descendente. O(k log n). Vacía el montículo en esos k. */
    public List<T> extraerK(int k) {
        List<T> top = new ArrayList<>(Math.min(k, datos.size()));
        for (int i = 0; i < k && !datos.isEmpty(); i++) top.add(extraerMax());
        return top;
    }

    public int tamano() {
        return datos.size();
    }

    public boolean estaVacio() {
        return datos.isEmpty();
    }

    private void subir(int i) {
        while (i > 0) {
            int padre = (i - 1) / 2;
            if (comparador.compare(datos.get(i), datos.get(padre)) <= 0) return;
            intercambiar(i, padre);
            i = padre;
        }
    }

    private void bajar(int i) {
        int n = datos.size();
        while (true) {
            int izq = 2 * i + 1, der = izq + 1, mayor = i;
            if (izq < n && comparador.compare(datos.get(izq), datos.get(mayor)) > 0) mayor = izq;
            if (der < n && comparador.compare(datos.get(der), datos.get(mayor)) > 0) mayor = der;
            if (mayor == i) return;
            intercambiar(i, mayor);
            i = mayor;
        }
    }

    private void intercambiar(int a, int b) {
        T t = datos.get(a);
        datos.set(a, datos.get(b));
        datos.set(b, t);
    }
}
