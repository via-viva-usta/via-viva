package viaviva.vista;

import java.awt.BorderLayout;
import java.awt.Color;
import java.awt.Dimension;
import java.awt.FlowLayout;
import java.awt.Font;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import javax.swing.BorderFactory;
import javax.swing.Box;
import javax.swing.BoxLayout;
import javax.swing.DefaultListModel;
import javax.swing.JButton;
import javax.swing.JCheckBox;
import javax.swing.JComboBox;
import javax.swing.JLabel;
import javax.swing.JList;
import javax.swing.JOptionPane;
import javax.swing.JPanel;
import javax.swing.JScrollPane;
import javax.swing.JSpinner;
import javax.swing.JTable;
import javax.swing.JTextArea;
import javax.swing.ListSelectionModel;
import javax.swing.SpinnerNumberModel;
import javax.swing.table.DefaultTableModel;
import viaviva.control.ControladorTablero;
import viaviva.estructuras.GrafoCalles;
import viaviva.estructuras.TablaHash;
import viaviva.modelo.Corrida;
import viaviva.modelo.Tramo;

/**
 * Contenido completo del tablero (sin el JFrame, para poder dibujarlo también fuera de pantalla).
 * Centro: mapa. Derecha: corrida, ranking (heap), corredor y zonas (BFS), detalle del tramo.
 */
public class PanelTablero extends JPanel {

    private final ControladorTablero ctl;
    private final PanelMapa mapa;
    private final JLabel avisoDemo = new JLabel();
    private final JComboBox<Corrida> comboCorrida = new JComboBox<>();
    private final JSpinner spK = new JSpinner(new SpinnerNumberModel(15, 1, 500, 1));
    private final JCheckBox chkNoReportados = new JCheckBox("Solo tramos no reportados", true);
    private final DefaultTableModel modeloRanking =
            new DefaultTableModel(new Object[]{"#", "Tramo", "Calle", "Barrio", "Riesgo"}, 0) {
                @Override
                public boolean isCellEditable(int r, int c) {
                    return false;
                }
            };
    private final JTable tablaRanking = new JTable(modeloRanking);
    private final List<Tramo> filasRanking = new ArrayList<>();
    private final JSpinner spSaltos = new JSpinner(new SpinnerNumberModel(3, 1, 30, 1));
    private final JSpinner spPercentil = new JSpinner(new SpinnerNumberModel(90, 50, 99, 1));
    private final DefaultListModel<String> modeloZonas = new DefaultListModel<>();
    private final JList<String> listaZonas = new JList<>(modeloZonas);
    private List<List<Tramo>> zonas = List.of();
    private final JTextArea detalle = new JTextArea(9, 30);
    private final JLabel estado = new JLabel();
    private Tramo seleccionado;

    public PanelTablero(ControladorTablero ctl) {
        super(new BorderLayout());
        this.ctl = ctl;
        this.mapa = new PanelMapa(ctl);

        avisoDemo.setOpaque(true);
        avisoDemo.setBackground(Paleta.AVISO_DEMO);
        avisoDemo.setForeground(Color.WHITE);
        avisoDemo.setFont(avisoDemo.getFont().deriveFont(Font.BOLD, 13f));
        avisoDemo.setBorder(BorderFactory.createEmptyBorder(6, 12, 6, 12));
        add(avisoDemo, BorderLayout.NORTH);
        add(mapa, BorderLayout.CENTER);
        add(construirLateral(), BorderLayout.EAST);
        estado.setBorder(BorderFactory.createEmptyBorder(4, 10, 4, 10));
        add(estado, BorderLayout.SOUTH);

        for (Corrida c : ctl.corridas()) comboCorrida.addItem(c);
        comboCorrida.setSelectedItem(ctl.corridaActual());
        comboCorrida.addActionListener(e -> cambiarCorrida());
        mapa.alSeleccionar(this::mostrarDetalle);
        actualizarTodo();
    }

    private JPanel construirLateral() {
        JPanel lado = new JPanel();
        lado.setLayout(new BoxLayout(lado, BoxLayout.Y_AXIS));
        lado.setPreferredSize(new Dimension(390, 600));
        lado.setBorder(BorderFactory.createEmptyBorder(8, 8, 8, 8));

        lado.add(seccion("Corrida del modelo de riesgo", comboCorrida));

        JPanel opcionesRanking = new JPanel(new FlowLayout(FlowLayout.LEFT, 4, 0));
        opcionesRanking.add(new JLabel("Top"));
        opcionesRanking.add(spK);
        opcionesRanking.add(chkNoReportados);
        spK.addChangeListener(e -> actualizarRanking());
        chkNoReportados.addActionListener(e -> actualizarRanking());
        tablaRanking.setSelectionMode(ListSelectionModel.SINGLE_SELECTION);
        tablaRanking.getColumnModel().getColumn(0).setMaxWidth(32);
        tablaRanking.getColumnModel().getColumn(1).setMaxWidth(52);
        tablaRanking.getColumnModel().getColumn(4).setMaxWidth(56);
        tablaRanking.getSelectionModel().addListSelectionListener(e -> {
            int f = tablaRanking.getSelectedRow();
            if (!e.getValueIsAdjusting() && f >= 0 && f < filasRanking.size()) {
                Tramo t = filasRanking.get(f);
                mapa.seleccionar(t, true);
                mostrarDetalle(t);
            }
        });
        JScrollPane scrollRanking = new JScrollPane(tablaRanking);
        scrollRanking.setPreferredSize(new Dimension(370, 210));
        JPanel ranking = new JPanel(new BorderLayout(0, 4));
        ranking.add(opcionesRanking, BorderLayout.NORTH);
        ranking.add(scrollRanking, BorderLayout.CENTER);
        lado.add(seccion("Ranking de tramos a revisar (montículo)", ranking));

        JPanel bfs = new JPanel(new FlowLayout(FlowLayout.LEFT, 4, 0));
        JButton btnCorredor = new JButton("Corredor del tramo");
        btnCorredor.addActionListener(e -> calcularCorredor());
        bfs.add(new JLabel("Saltos"));
        bfs.add(spSaltos);
        bfs.add(btnCorredor);
        lado.add(seccion("Corredor (BFS desde el tramo seleccionado)", bfs));

        JPanel zonasPanel = new JPanel(new BorderLayout(0, 4));
        JPanel filaZonas = new JPanel(new FlowLayout(FlowLayout.LEFT, 4, 0));
        JButton btnZonas = new JButton("Buscar zonas");
        btnZonas.addActionListener(e -> buscarZonas());
        filaZonas.add(new JLabel("Riesgo ≥ percentil"));
        filaZonas.add(spPercentil);
        filaZonas.add(btnZonas);
        listaZonas.setVisibleRowCount(5);
        listaZonas.addListSelectionListener(e -> {
            int i = listaZonas.getSelectedIndex();
            if (!e.getValueIsAdjusting() && i >= 0 && i < zonas.size()) mapa.mostrarZona(zonas.get(i));
        });
        zonasPanel.add(filaZonas, BorderLayout.NORTH);
        zonasPanel.add(new JScrollPane(listaZonas), BorderLayout.CENTER);
        lado.add(seccion("Zonas de alto riesgo (componentes conexas, BFS)", zonasPanel));

        detalle.setEditable(false);
        detalle.setLineWrap(true);
        detalle.setWrapStyleWord(true);
        detalle.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 11));
        lado.add(seccion("Detalle", new JScrollPane(detalle)));
        lado.add(Box.createVerticalGlue());
        return lado;
    }

    private static JPanel seccion(String titulo, java.awt.Component contenido) {
        JPanel p = new JPanel(new BorderLayout());
        p.setBorder(BorderFactory.createCompoundBorder(BorderFactory.createTitledBorder(titulo),
                BorderFactory.createEmptyBorder(2, 4, 4, 4)));
        p.add(contenido, BorderLayout.CENTER);
        p.setAlignmentX(LEFT_ALIGNMENT);
        p.setMaximumSize(new Dimension(Integer.MAX_VALUE, p.getPreferredSize().height + 400));
        return p;
    }

    private void cambiarCorrida() {
        Corrida c = (Corrida) comboCorrida.getSelectedItem();
        if (c == null || c.equals(ctl.corridaActual())) return;
        try {
            ctl.elegirCorrida(c);
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(this, ex.getMessage(), "Error al leer la corrida", JOptionPane.ERROR_MESSAGE);
        }
        zonas = List.of();
        modeloZonas.clear();
        mapa.mostrarZona(List.of());
        actualizarTodo();
    }

    private void actualizarTodo() {
        Corrida c = ctl.corridaActual();
        if (c == null) {
            avisoDemo.setText("Sin corridas en la tabla riesgo: el mapa muestra solo el grafo. "
                    + "Corre python -m risk_model.modelo --guardar");
            avisoDemo.setBackground(Paleta.ASFALTO);
            avisoDemo.setVisible(true);
        } else if (c.esDemo()) {
            avisoDemo.setText("DEMO: riesgo calculado con etiquetas INVENTADAS (" + c.version()
                    + "). Sirve para probar el tablero; NO es un resultado.");
            avisoDemo.setBackground(Paleta.AVISO_DEMO);
            avisoDemo.setVisible(true);
        } else {
            avisoDemo.setVisible(false);
        }
        actualizarRanking();
        TablaHash<Long, ?> ady = ctl.grafo().tablaAdyacencia();
        estado.setText(String.format(Locale.ROOT,
                "%d tramos · %d nodos · tabla hash de adyacencia: capacidad %d, colisiones %d, cadena más larga %d"
                        + " · índice geohash: %d celdas · carga %d ms · %s",
                ctl.tramos().size(), ctl.grafo().numNodos(), ady.capacidad(), ady.colisiones(), ady.cadenaMasLarga(),
                ctl.indice().numCeldas(), ctl.msCarga(), ctl.rutaDb()));
        mapa.repaint();
    }

    private void actualizarRanking() {
        modeloRanking.setRowCount(0);
        filasRanking.clear();
        long t0 = System.nanoTime();
        List<Tramo> top = ctl.topRiesgo((Integer) spK.getValue(), chkNoReportados.isSelected());
        double ms = (System.nanoTime() - t0) / 1e6;
        int i = 1;
        for (Tramo t : top) {
            filasRanking.add(t);
            modeloRanking.addRow(new Object[]{i++, t.id, t.nombreVisible(), t.barrio,
                String.format(Locale.ROOT, "%.3f", t.riesgo)});
        }
        if (!top.isEmpty()) {
            detalle.setText(String.format(Locale.ROOT,
                    "Ranking: montículo con los tramos con riesgo (O(n) al construir) y %d extracciones "
                            + "(O(k log n)) en %.2f ms.%nHaz clic en el mapa o en el ranking para ver un tramo.",
                    top.size(), ms));
        }
    }

    private void mostrarDetalle(Tramo t) {
        seleccionado = t;
        StringBuilder sb = new StringBuilder();
        sb.append("Tramo ").append(t.id).append("\n");
        sb.append("Calle:   ").append(t.nombreVisible()).append("\n");
        sb.append("Tipo:    ").append(t.tipoVia).append("\n");
        sb.append("Barrio:  ").append(t.barrio == null ? "—" : t.barrio).append("\n");
        sb.append(String.format(Locale.ROOT, "Largo:   %.0f m%n", t.longitudM));
        sb.append("Riesgo:  ").append(t.tieneRiesgo() ? String.format(Locale.ROOT, "%.3f", t.riesgo) : "sin dato")
                .append(t.reportado ? " (ya reportado)" : "").append("\n");
        sb.append(String.format(Locale.ROOT, "Centro:  %.6f, %.6f%n", t.latCentro, t.lonCentro));
        sb.append(String.format(Locale.ROOT, "OSM:     %d → %d%n", t.osmU, t.osmV));
        sb.append("\nBúsqueda por clic con índice geohash: ")
                .append(ctl.indice().comparacionesUltimaBusqueda())
                .append(" tramos comparados (fuerza bruta: ").append(ctl.tramos().size()).append(").");
        detalle.setText(sb.toString());
        detalle.setCaretPosition(0);
    }

    private void calcularCorredor() {
        if (seleccionado == null) {
            JOptionPane.showMessageDialog(this, "Primero selecciona un tramo en el mapa o en el ranking.");
            return;
        }
        int saltos = (Integer) spSaltos.getValue();
        long t0 = System.nanoTime();
        GrafoCalles.ResultadoBFS r = ctl.corredor(seleccionado, saltos);
        double ms = (System.nanoTime() - t0) / 1e6;
        mapa.mostrarCorredor(r.tramos());
        double conRiesgo = r.tramos().stream().filter(Tramo::tieneRiesgo).mapToDouble(t -> t.riesgo).average()
                .orElse(Double.NaN);
        detalle.setText(String.format(Locale.ROOT,
                "Corredor BFS desde el tramo %d, hasta %d intersecciones:%n  %d tramos, %.2f km, "
                        + "%d nodos visitados%n  riesgo medio %.3f%n  tiempo %.2f ms (O(V' + E') del vecindario)",
                seleccionado.id, saltos, r.tramos().size(), GrafoCalles.longitudTotal(r.tramos()) / 1000,
                r.nodosVisitados(), conRiesgo, ms));
    }

    private void buscarZonas() {
        if (ctl.corridaActual() == null) return;
        double p = ((Integer) spPercentil.getValue()).doubleValue();
        double umbral = ctl.percentilRiesgo(p);
        long t0 = System.nanoTime();
        zonas = ctl.zonasDeRiesgo(umbral);
        double ms = (System.nanoTime() - t0) / 1e6;
        modeloZonas.clear();
        for (int i = 0; i < zonas.size(); i++) {
            List<Tramo> z = zonas.get(i);
            double media = z.stream().mapToDouble(t -> t.riesgo).average().orElse(0);
            modeloZonas.addElement(String.format(Locale.ROOT, "Zona %d: %d tramos, %.2f km, riesgo medio %.3f",
                    i + 1, z.size(), GrafoCalles.longitudTotal(z) / 1000, media));
        }
        detalle.setText(String.format(Locale.ROOT,
                "Zonas: componentes conexas de los tramos con riesgo ≥ %.3f (percentil %.0f).%n"
                        + "%d zonas encontradas con BFS en %.2f ms (O(V + E)).%nSelecciona una para verla.",
                umbral, p, zonas.size(), ms));
    }

    // ---- usados por la captura sin pantalla ----
    public PanelMapa mapa() {
        return mapa;
    }

    public void seleccionarPrimeroDelRanking() {
        if (!filasRanking.isEmpty()) tablaRanking.setRowSelectionInterval(0, 0);
    }

    public void ejecutarCorredor() {
        calcularCorredor();
    }

    public void ejecutarZonas() {
        buscarZonas();
        if (!zonas.isEmpty()) listaZonas.setSelectedIndex(0);
    }
}
