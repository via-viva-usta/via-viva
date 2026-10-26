package viaviva.modelo;

/** Una corrida del modelo de riesgo guardada en la tabla riesgo. */
public record Corrida(String modelo, String version, String fecha, int tramos) {

    /** Las corridas de prueba con etiquetas inventadas no son resultados: el tablero lo advierte. */
    public boolean esDemo() {
        return version != null && version.toUpperCase().startsWith("DEMO");
    }

    @Override
    public String toString() {
        return modelo + " · " + version + " · " + fecha + (esDemo() ? "  [DEMO]" : "");
    }
}
