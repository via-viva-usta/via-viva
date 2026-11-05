package viaviva.vista;

import java.awt.BorderLayout;
import java.awt.CardLayout;
import java.awt.Color;
import java.awt.Component;
import java.awt.FlowLayout;
import java.awt.Font;
import java.awt.Graphics2D;
import java.awt.Image;
import java.awt.RenderingHints;
import java.awt.event.MouseAdapter;
import java.awt.event.MouseEvent;
import java.awt.image.BufferedImage;
import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import javax.imageio.ImageIO;
import javax.swing.BorderFactory;
import javax.swing.ImageIcon;
import javax.swing.JLabel;
import javax.swing.JOptionPane;
import javax.swing.JPanel;
import javax.swing.JScrollPane;
import javax.swing.JSpinner;
import javax.swing.JTable;
import javax.swing.ListSelectionModel;
import javax.swing.SpinnerNumberModel;
import javax.swing.SwingConstants;
import javax.swing.table.DefaultTableModel;
import javax.swing.table.TableCellRenderer;
import viaviva.control.ControladorTablero;
import viaviva.estructuras.TablaHash;
import viaviva.modelo.Peligro;

/**
 * Pestaña "Reportes y eventos": reportes ciudadanos (bot) y eventos de la vía (nodo / phyphox) en orden de atención,
 * prioridad = severidad × tránsito × reincidencia, sacados del montículo. Lo DEMO lleva la marca y fondo rojo claro.
 * Si no hay ninguno muestra un estado vacío que explica de dónde llegan los datos.
 */
public class PanelPeligros extends JPanel {

    private static final int MINI_ANCHO = 64, MINI_ALTO = 48;
    private static final int COL_DEMO = 1, COL_FOTO = 11;
    private static final Color FONDO_DEMO = new Color(0xFBE3E1);

    private final ControladorTablero ctl;
    private final JLabel resumen = new JLabel();
    private final JSpinner spK = new JSpinner(new SpinnerNumberModel(100, 1, 100_000, 10));
    private final DefaultTableModel modelo = new DefaultTableModel(new Object[]{"#", "Marca", "Fuente", "Clase",
        "Sev.", "Tramo", "Vía (peso)", "Reinc.", "Prioridad", "Fecha (UTC)", "Estado", "Foto"}, 0) {
        @Override
        public boolean isCellEditable(int r, int c) {
            return false;
        }

        @Override
        public Class<?> getColumnClass(int c) {
            return c == COL_FOTO ? Object.class : String.class;
        }
    };
    private final JTable tabla;
    private final List<Peligro> filas = new ArrayList<>();
    private final CardLayout tarjetas = new CardLayout();
    private final JPanel centro = new JPanel(tarjetas);
    private final JLabel mensajeVacio = new JLabel("", SwingConstants.CENTER);
    /** Miniaturas ya leídas: ruta del archivo → ícono (tabla hash propia). */
    private final TablaHash<String, ImageIcon> miniaturas = new TablaHash<>();
    private Consumer<Peligro> alIrAlMapa = p -> { };

    public PanelPeligros(ControladorTablero ctl) {
        super(new BorderLayout(0, 6));
        this.ctl = ctl;
        setBorder(BorderFactory.createEmptyBorder(8, 10, 8, 10));

        tabla = new JTable(modelo) {
            @Override
            public Component prepareRenderer(TableCellRenderer r, int fila, int col) {
                Component c = super.prepareRenderer(r, fila, col);
                if (!isRowSelected(fila) && fila < filas.size()) {
                    c.setBackground(filas.get(fila).demo ? FONDO_DEMO : getBackground());
                }
                if (col == COL_DEMO && fila < filas.size() && filas.get(fila).demo) {
                    c.setForeground(Paleta.AVISO_DEMO);
                    c.setFont(c.getFont().deriveFont(Font.BOLD));
                } else if (!isRowSelected(fila)) {
                    c.setForeground(getForeground());
                }
                return c;
            }
        };
        tabla.setDefaultRenderer(Object.class, new RenderizadorFoto());
        tabla.setSelectionMode(ListSelectionModel.SINGLE_SELECTION);
        tabla.setRowHeight(MINI_ALTO + 4);
        int[] anchos = {34, 52, 64, 100, 84, 60, 120, 50, 62, 120, 96, MINI_ANCHO + 10};
        for (int i = 0; i < anchos.length; i++) tabla.getColumnModel().getColumn(i).setPreferredWidth(anchos[i]);
        tabla.addMouseListener(new MouseAdapter() {
            @Override
            public void mouseClicked(MouseEvent e) {
                int f = tabla.rowAtPoint(e.getPoint()), c = tabla.columnAtPoint(e.getPoint());
                if (e.getClickCount() != 2 || f < 0 || f >= filas.size()) return;
                if (c == COL_FOTO) verFoto(filas.get(f));
                else alIrAlMapa.accept(filas.get(f));
            }
        });

        JPanel arriba = new JPanel(new BorderLayout(0, 4));
        JPanel opciones = new JPanel(new FlowLayout(FlowLayout.LEFT, 6, 0));
        opciones.add(new JLabel("Mostrar los"));
        opciones.add(spK);
        opciones.add(new JLabel("de mayor prioridad · prioridad = severidad (1–3) × tránsito (1–3) × reincidencia"
                + " · doble clic: ver el tramo en el mapa (o la foto)"));
        spK.addChangeListener(e -> actualizar());
        arriba.add(resumen, BorderLayout.NORTH);
        arriba.add(opciones, BorderLayout.SOUTH);
        add(arriba, BorderLayout.NORTH);

        mensajeVacio.setFont(mensajeVacio.getFont().deriveFont(14f));
        mensajeVacio.setForeground(Paleta.ASFALTO);
        centro.add(new JScrollPane(tabla), "lista");
        centro.add(mensajeVacio, "vacio");
        add(centro, BorderLayout.CENTER);
        actualizar();
    }

    /** Qué hacer al pedir un peligro en el mapa (lo pone el PanelTablero). */
    public void alIrAlMapa(Consumer<Peligro> accion) {
        this.alIrAlMapa = accion;
    }

    public int cantidad() {
        return ctl.peligros().size();
    }

    public void actualizar() {
        List<Peligro> todos = ctl.peligros();
        int reportes = 0, eventos = 0, demos = 0, sinTramo = 0;
        for (Peligro p : todos) {
            if (p.fuente == Peligro.Fuente.REPORTE) reportes++;
            else eventos++;
            if (p.demo) demos++;
            if (p.tramo == null) sinTramo++;
        }
        String noVia = ctl.eventosNoVia() > 0
                ? " · " + ctl.eventosNoVia() + " eventos de maniobra o 'normal' no se listan" : "";
        resumen.setText(String.format(Locale.ROOT, "%d reportes ciudadanos · %d eventos de la vía · %d DEMO · "
                + "%d sin tramo a ≤ %.0f m (* = tramo hallado con el índice geohash)%s · lectura y prioridad en %.1f ms",
                reportes, eventos, demos, sinTramo, ControladorTablero.MAX_DIST_TRAMO_M, noVia, ctl.msPeligros()));

        modelo.setRowCount(0);
        filas.clear();
        if (ctl.errorPeligros() != null) {
            mostrarVacio("No se pudieron leer los reportes y eventos de la base.",
                    "Detalle: " + ctl.errorPeligros(), "El resto del tablero funciona igual.");
            return;
        }
        if (todos.isEmpty()) {
            mostrarVacio("Todavía no hay reportes ciudadanos ni eventos de la vía en la base.",
                    "Los reportes llegan con el bot de Telegram (/reportar) y los eventos con los recorridos "
                            + "(python -m etl.recorridos) o con el nodo.",
                    "Base: " + ctl.rutaDb());
            return;
        }
        int i = 1;
        for (Peligro p : ctl.peligrosPriorizados((Integer) spK.getValue())) {
            filas.add(p);
            modelo.addRow(new Object[]{i++, p.demo ? "DEMO" : "", p.fuente.toString(), p.clase,
                textoSeveridad(p), textoTramo(p), textoVia(p), String.valueOf(p.reincidencia),
                String.valueOf(p.prioridad), p.fechaCorta(), textoEstado(p), miniatura(p)});
        }
        tarjetas.show(centro, "lista");
    }

    private void mostrarVacio(String titulo, String linea2, String linea3) {
        mensajeVacio.setText("<html><div style='text-align:center'><b>" + escapar(titulo) + "</b><br><br>"
                + escapar(linea2) + "<br>" + escapar(linea3) + "</div></html>");
        tarjetas.show(centro, "vacio");
    }

    private static String escapar(String s) {
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");
    }

    private static String textoSeveridad(Peligro p) {
        String n = switch (p.nivelSeveridad) {
            case 1 -> "1 leve";
            case 2 -> "2 media";
            default -> "3 alta";
        };
        return p.severidad01 == null ? n : n + String.format(Locale.ROOT, " (%.2f)", p.severidad01);
    }

    private static String textoTramo(Peligro p) {
        if (p.tramo == null) return "sin tramo";
        return p.tramo.id + (p.tramoPorIndice ? " *" : "");
    }

    private static String textoVia(Peligro p) {
        if (p.tramo == null) return "— (1)";
        return p.tramo.tipoVia + " (" + p.pesoTransito + ")";
    }

    private static String textoEstado(Peligro p) {
        if (p.fuente == Peligro.Fuente.EVENTO) return p.origen;   // nodo, phyphox o simulado
        return p.estado == null ? "—" : p.estado.replace('_', ' ');
    }

    /** Miniatura de la foto (o un texto si no hay o no se encuentra). */
    private Object miniatura(Peligro p) {
        if (!p.tieneFoto()) return "sin foto";
        File f = ctl.archivoFoto(p);
        if (f == null) return "no está";
        String llave = f.getAbsolutePath();
        ImageIcon icono = miniaturas.obtener(llave);
        if (icono == null) {
            icono = leerEscalada(f, MINI_ANCHO, MINI_ALTO);
            if (icono == null) return "no se lee";
            miniaturas.poner(llave, icono);
        }
        return icono;
    }

    private static ImageIcon leerEscalada(File f, int anchoMax, int altoMax) {
        try {
            BufferedImage img = ImageIO.read(f);
            if (img == null) return null;
            double esc = Math.min((double) anchoMax / img.getWidth(), (double) altoMax / img.getHeight());
            int w = Math.max(1, (int) Math.round(img.getWidth() * esc));
            int h = Math.max(1, (int) Math.round(img.getHeight() * esc));
            BufferedImage chica = new BufferedImage(w, h, BufferedImage.TYPE_INT_RGB);
            Graphics2D g = chica.createGraphics();
            g.setRenderingHint(RenderingHints.KEY_INTERPOLATION, RenderingHints.VALUE_INTERPOLATION_BILINEAR);
            g.drawImage(img, 0, 0, w, h, null);
            g.dispose();
            return new ImageIcon(chica);
        } catch (Exception ex) {
            return null;
        }
    }

    private void verFoto(Peligro p) {
        File f = ctl.archivoFoto(p);
        if (f == null) {
            JOptionPane.showMessageDialog(this, p.tieneFoto() ? "No se encontró la foto: " + p.fotoRuta : "Sin foto.");
            return;
        }
        ImageIcon grande = leerEscalada(f, 800, 600);
        if (grande == null) {
            JOptionPane.showMessageDialog(this, "No se pudo leer la foto: " + f);
            return;
        }
        JOptionPane.showMessageDialog(this, new JLabel(grande), p + (p.demo ? " — DEMO, no es un resultado" : ""),
                JOptionPane.PLAIN_MESSAGE);
    }

    /** La columna Foto puede traer un ícono (miniatura) o un texto. */
    private static final class RenderizadorFoto extends javax.swing.table.DefaultTableCellRenderer {
        @Override
        public Component getTableCellRendererComponent(JTable t, Object v, boolean sel, boolean foco, int f, int c) {
            super.getTableCellRendererComponent(t, v instanceof Image || v instanceof ImageIcon ? "" : v, sel, foco, f, c);
            setIcon(v instanceof ImageIcon i ? i : null);
            setHorizontalAlignment(v instanceof ImageIcon ? SwingConstants.CENTER : SwingConstants.LEADING);
            return this;
        }
    }
}
