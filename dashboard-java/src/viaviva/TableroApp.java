package viaviva;

import java.awt.Component;
import java.awt.Container;
import java.awt.Graphics2D;
import java.awt.image.BufferedImage;
import java.io.File;
import javax.imageio.ImageIO;
import javax.swing.JFileChooser;
import javax.swing.JFrame;
import javax.swing.JOptionPane;
import javax.swing.SwingUtilities;
import javax.swing.UIManager;
import javax.swing.filechooser.FileNameExtensionFilter;
import viaviva.control.ControladorTablero;
import viaviva.vista.PanelTablero;

/**
 * Tablero VÍA VIVA para la autoridad.
 *
 * <pre>
 * Uso:  java -jar TableroViaViva.jar [ruta/a/via_viva.db]
 *       java -jar TableroViaViva.jar [ruta/a/via_viva.db] --captura salida.png   (imagen sin abrir ventana)
 *       java -jar TableroViaViva.jar [ruta/a/via_viva.db] --captura salida.png --pestana reportes
 * </pre>
 * Sin ruta, busca ../data/via_viva.db (desde dashboard-java/) y data/via_viva.db; si no la encuentra, pregunta.
 */
public class TableroApp {

    public static void main(String[] args) throws Exception {
        String ruta = null, captura = null;
        boolean pestanaReportes = false;
        for (int i = 0; i < args.length; i++) {
            if (args[i].equals("--captura") && i + 1 < args.length) captura = args[++i];
            else if (args[i].equals("--pestana") && i + 1 < args.length) pestanaReportes = args[++i].startsWith("reporte");
            else ruta = args[i];
        }
        if (ruta == null) ruta = buscarBase();

        if (captura != null) {
            System.setProperty("java.awt.headless", "true");
            capturar(ruta, new File(captura), pestanaReportes);
            return;
        }
        final String rutaFinal = ruta;
        SwingUtilities.invokeLater(() -> abrirVentana(rutaFinal));
    }

    private static String buscarBase() {
        for (String c : new String[]{"../data/via_viva.db", "data/via_viva.db"}) {
            if (new File(c).isFile()) return new File(c).getAbsolutePath();
        }
        return null;
    }

    private static void abrirVentana(String ruta) {
        try {
            UIManager.setLookAndFeel(UIManager.getSystemLookAndFeelClassName());
        } catch (Exception ignorada) {
            // se queda el aspecto por defecto
        }
        if (ruta == null) {
            JFileChooser fc = new JFileChooser(new File("."));
            fc.setDialogTitle("Elige la base de VÍA VIVA (via_viva.db)");
            fc.setFileFilter(new FileNameExtensionFilter("Base SQLite", "db", "sqlite"));
            if (fc.showOpenDialog(null) != JFileChooser.APPROVE_OPTION) System.exit(0);
            ruta = fc.getSelectedFile().getAbsolutePath();
        }
        try {
            ControladorTablero ctl = new ControladorTablero(ruta);
            ctl.cargar();
            PanelTablero panel = new PanelTablero(ctl);
            JFrame ventana = new JFrame("VÍA VIVA · Tablero de riesgo vial · Tunja");
            ventana.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
            ventana.setContentPane(panel);
            ventana.setSize(1400, 900);
            ventana.setLocationRelativeTo(null);
            ventana.setVisible(true);
            SwingUtilities.invokeLater(() -> panel.mapa().ajustarVista(panel.mapa().getWidth(),
                    panel.mapa().getHeight()));
        } catch (Exception ex) {
            JOptionPane.showMessageDialog(null, "No se pudo abrir " + ruta + ":\n" + ex.getMessage(),
                    "VÍA VIVA", JOptionPane.ERROR_MESSAGE);
            System.exit(1);
        }
    }

    /** Dibuja el tablero completo en un PNG sin mostrar ventanas (sirve para documentar y para probar). */
    private static void capturar(String ruta, File salida, boolean pestanaReportes) throws Exception {
        if (ruta == null) throw new IllegalArgumentException("No se encontró via_viva.db; pásala como argumento.");
        ControladorTablero ctl = new ControladorTablero(ruta);
        ctl.cargar();
        PanelTablero panel = new PanelTablero(ctl);
        int ancho = 1400, alto = 900;
        panel.setSize(ancho, alto);
        acomodar(panel);
        panel.mapa().ajustarVista(panel.mapa().getWidth(), panel.mapa().getHeight());
        panel.seleccionarPrimeroDelRanking();
        panel.ejecutarCorredor();
        acomodar(panel);
        panel.mapa().ajustarVista(panel.mapa().getWidth(), panel.mapa().getHeight());   // ciudad completa
        if (pestanaReportes) {
            panel.mostrarPestanaPeligros();
            acomodar(panel);
        }
        BufferedImage img = new BufferedImage(ancho, alto, BufferedImage.TYPE_INT_RGB);
        Graphics2D g = img.createGraphics();
        panel.paint(g);
        g.dispose();
        ImageIO.write(img, "png", salida);
        System.out.println("Captura guardada en " + salida.getAbsolutePath());
    }

    private static void acomodar(Component c) {
        if (c instanceof Container k) {
            k.doLayout();
            for (Component h : k.getComponents()) acomodar(h);
        }
    }
}
