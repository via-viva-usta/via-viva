package viaviva.vista;

import java.awt.BasicStroke;
import java.awt.Color;
import java.awt.Dimension;
import java.awt.Font;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.Shape;
import java.awt.event.MouseAdapter;
import java.awt.event.MouseEvent;
import java.awt.event.MouseWheelEvent;
import java.awt.geom.AffineTransform;
import java.awt.geom.Path2D;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.function.Consumer;
import javax.swing.JPanel;
import viaviva.control.ControladorTablero;
import viaviva.modelo.Tramo;

/** Dibuja el grafo de Tunja: tramos coloreados por riesgo, corredor BFS, zona y tramo seleccionado. */
public class PanelMapa extends JPanel {

    private final ControladorTablero ctl;
    private final List<Path2D> caminos = new ArrayList<>();   // geometría en metros, una por tramo
    private double escala = 0.05;      // píxeles por metro
    private double centroX, centroY;   // metros en el centro de la vista
    private Tramo seleccionado;
    private Set<Integer> corredor = new HashSet<>();
    private Set<Integer> zona = new HashSet<>();
    private Consumer<Tramo> alSeleccionar = t -> { };
    private int arrastreX, arrastreY;

    public PanelMapa(ControladorTablero ctl) {
        this.ctl = ctl;
        setBackground(Paleta.FONDO);
        setPreferredSize(new Dimension(900, 700));
        for (Tramo t : ctl.tramos()) {
            Path2D p = new Path2D.Double();
            p.moveTo(t.xs[0], t.ys[0]);
            for (int i = 1; i < t.xs.length; i++) p.lineTo(t.xs[i], t.ys[i]);
            caminos.add(p);
        }
        MouseAdapter raton = new MouseAdapter() {
            @Override
            public void mousePressed(MouseEvent e) {
                arrastreX = e.getX();
                arrastreY = e.getY();
            }

            @Override
            public void mouseDragged(MouseEvent e) {
                centroX -= (e.getX() - arrastreX) / escala;
                centroY += (e.getY() - arrastreY) / escala;
                arrastreX = e.getX();
                arrastreY = e.getY();
                repaint();
            }

            @Override
            public void mouseClicked(MouseEvent e) {
                double[] m = aMetros(e.getX(), e.getY());
                // tolerancia ~12 px, máximo 100 m: menos que una celda geohash de precisión 7 (~153 m)
                Tramo t = ctl.tramoCercano(m[0], m[1], Math.min(100, 12 / escala + 5));
                if (t != null) {
                    seleccionar(t, false);
                    alSeleccionar.accept(t);
                }
            }

            @Override
            public void mouseWheelMoved(MouseWheelEvent e) {
                double[] antes = aMetros(e.getX(), e.getY());
                escala *= Math.pow(1.2, -e.getPreciseWheelRotation());
                escala = Math.max(0.005, Math.min(escala, 20));
                double[] despues = aMetros(e.getX(), e.getY());
                centroX += antes[0] - despues[0];
                centroY += antes[1] - despues[1];
                repaint();
            }
        };
        addMouseListener(raton);
        addMouseMotionListener(raton);
        addMouseWheelListener(raton);
    }

    public void alSeleccionar(Consumer<Tramo> accion) {
        this.alSeleccionar = accion;
    }

    /** Ajusta la vista para ver la zona urbana (percentiles 2-98 de los centros, para no encoger por las veredas). */
    public void ajustarVista(int ancho, int alto) {
        List<Tramo> ts = ctl.tramos();
        double[] xs = new double[ts.size()], ys = new double[ts.size()];
        for (int i = 0; i < ts.size(); i++) {
            xs[i] = ts.get(i).xs[0];
            ys[i] = ts.get(i).ys[0];
        }
        java.util.Arrays.sort(xs);
        java.util.Arrays.sort(ys);
        int a = xs.length * 2 / 100, b = xs.length * 98 / 100;
        centroX = (xs[a] + xs[b]) / 2;
        centroY = (ys[a] + ys[b]) / 2;
        escala = 0.92 * Math.min(ancho / (xs[b] - xs[a]), alto / (ys[b] - ys[a]));
        repaint();
    }

    public void seleccionar(Tramo t, boolean centrar) {
        seleccionado = t;
        if (centrar && t != null) {
            centroX = t.xs[t.xs.length / 2];
            centroY = t.ys[t.ys.length / 2];
            escala = Math.max(escala, 0.6);
        }
        repaint();
    }

    public void mostrarCorredor(List<Tramo> tramos) {
        corredor = new HashSet<>();
        for (Tramo t : tramos) corredor.add(t.id);
        repaint();
    }

    public void mostrarZona(List<Tramo> tramos) {
        zona = new HashSet<>();
        for (Tramo t : tramos) zona.add(t.id);
        if (!tramos.isEmpty()) seleccionar(tramos.get(0), true);
        repaint();
    }

    private AffineTransform transformacion() {
        AffineTransform at = new AffineTransform();
        at.translate(getWidth() / 2.0, getHeight() / 2.0);
        at.scale(escala, -escala);              // el eje y de la pantalla crece hacia abajo
        at.translate(-centroX, -centroY);
        return at;
    }

    private double[] aMetros(int px, int py) {
        return new double[]{centroX + (px - getWidth() / 2.0) / escala, centroY - (py - getHeight() / 2.0) / escala};
    }

    @Override
    protected void paintComponent(Graphics g0) {
        super.paintComponent(g0);
        Graphics2D g = (Graphics2D) g0.create();
        g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
        g.setRenderingHint(RenderingHints.KEY_STROKE_CONTROL, RenderingHints.VALUE_STROKE_PURE);
        AffineTransform at = transformacion();
        List<Tramo> ts = ctl.tramos();

        // 1) tramos sin riesgo y por quintil, de bajo a alto (los de más riesgo quedan encima)
        for (int clase = -1; clase <= 4; clase++) {
            g.setColor(clase < 0 ? Paleta.SIN_DATOS : Paleta.RIESGO[clase]);
            g.setStroke(new BasicStroke(clase < 0 ? 0.8f : Paleta.GROSOR[clase], BasicStroke.CAP_ROUND,
                    BasicStroke.JOIN_ROUND));
            for (int i = 0; i < ts.size(); i++) {
                if (ctl.claseRiesgo(ts.get(i)) == clase) g.draw(at.createTransformedShape(caminos.get(i)));
            }
        }
        // 2) zona de alto riesgo, 3) corredor BFS, 4) tramo seleccionado
        dibujarConjunto(g, at, zona, Paleta.ZONA, 5f);
        dibujarConjunto(g, at, corredor, Paleta.CORREDOR, 3.5f);
        if (seleccionado != null) {
            Shape s = at.createTransformedShape(caminos.get(ctl.tramos().indexOf(seleccionado)));
            g.setStroke(new BasicStroke(8f, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND));
            g.setColor(Color.WHITE);
            g.draw(s);
            g.setStroke(new BasicStroke(5f, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND));
            g.setColor(Paleta.SELECCION);
            g.draw(s);
        }
        dibujarLeyenda(g);
        dibujarEscala(g);
        g.dispose();
    }

    private void dibujarConjunto(Graphics2D g, AffineTransform at, Set<Integer> ids, Color color, float grosor) {
        if (ids.isEmpty()) return;
        g.setColor(color);
        g.setStroke(new BasicStroke(grosor, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND));
        List<Tramo> ts = ctl.tramos();
        for (int i = 0; i < ts.size(); i++) {
            if (ids.contains(ts.get(i).id)) g.draw(at.createTransformedShape(caminos.get(i)));
        }
    }

    private void dibujarLeyenda(Graphics2D g) {
        double[] cortes = ctl.cortesQuintiles();
        boolean hay = ctl.corridaActual() != null;
        int x = 14, alto = hay ? 7 * 18 + 26 : 2 * 18 + 26, y = getHeight() - alto - 14;
        g.setColor(new Color(255, 255, 255, 225));
        g.fillRoundRect(x, y, 232, alto, 10, 10);
        g.setColor(Paleta.ASFALTO);
        g.setFont(getFont().deriveFont(Font.BOLD, 12f));
        g.drawString("Riesgo de hueco no reportado", x + 10, y + 18);
        g.setFont(getFont().deriveFont(11f));
        int fila = y + 36;
        if (hay) {
            String[] rangos = new String[5];
            for (int c = 0; c < 5; c++) {
                String lo = c == 0 ? "mín" : String.format(Locale.ROOT, "%.2f", cortes[c - 1]);
                String hi = c == 4 ? "máx" : String.format(Locale.ROOT, "%.2f", cortes[c]);
                rangos[c] = "Quintil " + (c + 1) + "  (" + lo + " – " + hi + ")";
            }
            for (int c = 4; c >= 0; c--) {
                g.setColor(Paleta.RIESGO[c]);
                g.setStroke(new BasicStroke(Paleta.GROSOR[c] + 1.5f));
                g.drawLine(x + 10, fila - 4, x + 40, fila - 4);
                g.setColor(Paleta.ASFALTO);
                g.drawString(rangos[c], x + 48, fila);
                fila += 18;
            }
        }
        g.setColor(Paleta.SIN_DATOS);
        g.setStroke(new BasicStroke(2f));
        g.drawLine(x + 10, fila - 4, x + 40, fila - 4);
        g.setColor(Paleta.ASFALTO);
        g.drawString("Sin riesgo calculado", x + 48, fila);
        fila += 18;
        g.setColor(Paleta.CORREDOR);
        g.setStroke(new BasicStroke(3.5f));
        g.drawLine(x + 10, fila - 4, x + 40, fila - 4);
        g.setColor(Paleta.ASFALTO);
        g.drawString("Corredor (BFS)    ", x + 48, fila);
        g.setColor(Paleta.ZONA);
        g.drawLine(x + 140, fila - 4, x + 160, fila - 4);
        g.setColor(Paleta.ASFALTO);
        g.drawString("Zona", x + 166, fila);
    }

    private void dibujarEscala(Graphics2D g) {
        double[] opciones = {50, 100, 200, 500, 1000, 2000, 5000};
        double metros = opciones[0];
        for (double o : opciones) if (o * escala <= 160) metros = o;
        int px = (int) Math.round(metros * escala);
        int x = getWidth() - px - 24, y = getHeight() - 22;
        g.setColor(Paleta.ASFALTO);
        g.setStroke(new BasicStroke(2f));
        g.drawLine(x, y, x + px, y);
        g.drawLine(x, y - 5, x, y + 5);
        g.drawLine(x + px, y - 5, x + px, y + 5);
        g.setFont(getFont().deriveFont(11f));
        g.drawString(metros >= 1000 ? (int) (metros / 1000) + " km" : (int) metros + " m", x, y - 8);
    }
}
