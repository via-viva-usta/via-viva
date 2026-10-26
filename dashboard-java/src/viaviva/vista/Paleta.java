package viaviva.vista;

import java.awt.Color;

/**
 * Colores del tablero (identidad: gris asfalto, amarillo señal, verde azulado).
 * El riesgo se codifica con color Y grosor de línea, y los colores van de claro a oscuro,
 * para que se lea también con daltonismo.
 */
public final class Paleta {

    private Paleta() {
    }

    public static final Color FONDO = new Color(0xF4F3EF);
    public static final Color ASFALTO = new Color(0x3A3A3A);
    public static final Color SIN_DATOS = new Color(0xC4C4C4);
    public static final Color CORREDOR = new Color(0x1F78B4);
    public static final Color SELECCION = new Color(0x08306B);
    public static final Color ZONA = new Color(0x2A9D8F);       // verde azulado
    public static final Color AVISO_DEMO = new Color(0xB3261E);

    /** Quintiles de riesgo, de bajo a alto: amarillo señal → rojo oscuro. */
    public static final Color[] RIESGO = {
        new Color(0xF6D55C), new Color(0xF3A33A), new Color(0xE9672B), new Color(0xC8331F), new Color(0x7F0D1E)
    };
    public static final float[] GROSOR = {1.0f, 1.3f, 1.7f, 2.3f, 3.2f};
}
