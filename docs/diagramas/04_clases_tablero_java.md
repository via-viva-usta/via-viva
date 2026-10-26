# Clases UML del tablero Java

Proyecto NetBeans *Java with Ant*, Java 21, Swing (`dashboard-java/`). Lee la base SQLite con JDBC (`sqlite-jdbc` en `lib/`).
Las estructuras del curso se implementan a mano (`TablaHash`, `MonticuloMax`, `GrafoCalles`) para poder analizar su complejidad.

## Implementado (Fase 5)

```mermaid
classDiagram
    direction LR

    class TableroApp {
        +main(String[] args)$
        -capturar(String ruta, File salida)$
    }
    class ControladorTablero {
        -TablaHash~Integer, Tramo~ porId
        -GrafoCalles grafo
        -IndiceGeohash indice
        -Proyeccion proyeccion
        -Corrida corridaActual
        +cargar()
        +elegirCorrida(Corrida c)
        +topRiesgo(int k, boolean soloNoReportados) List~Tramo~
        +corredor(Tramo t, int saltos) ResultadoBFS
        +zonasDeRiesgo(double umbral) List~List~Tramo~~
        +tramoCercano(double x, double y, double maxM) Tramo
        +claseRiesgo(Tramo t) int
    }
    class RepositorioSQLite {
        +leerTramos() List~Tramo~
        +listarCorridas() List~Corrida~
        +aplicarRiesgo(Corrida c, TablaHash porId) int
    }
    class Tramo {
        +int id
        +long osmU
        +long osmV
        +String nombre
        +String tipoVia
        +double longitudM
        +double[] lats
        +double[] lons
        +double[] xs
        +double[] ys
        +double riesgo
        +boolean reportado
    }
    class Corrida {
        <<record>>
        +String modelo
        +String version
        +String fecha
        +esDemo() boolean
    }
    class Proyeccion {
        +aMetros(double lat, double lon) double[]
        +aGrados(double x, double y) double[]
        +proyectar(Tramo t)
    }

    class TablaHash~K, V~ {
        -Entrada[] cubetas
        -int tamano
        +poner(K llave, V valor) V
        +obtener(K llave) V
        +quitar(K llave) V
        +contiene(K llave) boolean
        -redimensionar()
        +cadenaMasLarga() int
    }
    class MonticuloMax~T~ {
        -List~T~ datos
        +MonticuloMax(Collection elementos, Comparator c)
        +insertar(T x)
        +extraerMax() T
        +extraerK(int k) List~T~
        -subir(int i)
        -bajar(int i)
    }
    class GrafoCalles {
        -TablaHash~Long, List~Arista~~ adyacencia
        +agregarTramo(Tramo t)
        +vecinos(long nodo) List~Arista~
        +corredor(Tramo origen, int maxSaltos) ResultadoBFS
        +zonasDeRiesgo(double umbral) List~List~Tramo~~
    }
    class Arista {
        <<record>>
        +long destino
        +Tramo tramo
    }
    class IndiceGeohash {
        -TablaHash~String, List~Tramo~~ celdas
        +insertar(Tramo t)
        +masCercano(double lat, double lon, Proyeccion p, double maxM) Tramo
        +masCercanoFuerzaBruta(double lat, double lon, Proyeccion p, double maxM) Tramo
    }
    class Geohash {
        +codificar(double lat, double lon, int precision)$ String
        +celdaYVecinas(String geohash)$ String[]
    }

    class PanelTablero {
        -PanelMapa mapa
        -JTable tablaRanking
        -JList listaZonas
    }
    class PanelMapa {
        +ajustarVista(int ancho, int alto)
        +seleccionar(Tramo t, boolean centrar)
        +mostrarCorredor(List~Tramo~ tramos)
        +mostrarZona(List~Tramo~ tramos)
        #paintComponent(Graphics g)
    }
    class PruebaEstructuras {
        +main(String[] args)$
    }

    TableroApp ..> ControladorTablero : crea
    TableroApp ..> PanelTablero : crea
    PanelTablero *-- PanelMapa
    PanelTablero --> ControladorTablero
    PanelMapa --> ControladorTablero
    ControladorTablero ..> RepositorioSQLite : usa
    ControladorTablero *-- GrafoCalles
    ControladorTablero *-- IndiceGeohash
    ControladorTablero *-- TablaHash
    ControladorTablero ..> MonticuloMax : ranking
    ControladorTablero --> Proyeccion
    ControladorTablero o-- Corrida
    GrafoCalles *-- TablaHash
    GrafoCalles *-- Arista
    Arista --> Tramo
    IndiceGeohash *-- TablaHash
    IndiceGeohash ..> Geohash
    RepositorioSQLite ..> Tramo
    RepositorioSQLite ..> Corrida
    PruebaEstructuras ..> ControladorTablero
    JPanel <|-- PanelTablero
    JPanel <|-- PanelMapa
```

## Pendiente (cuando haya eventos del nodo y reportes del bot)

| Clase | Estructura | Para qué |
|---|---|---|
| `Evento`, `Reporte`, `Peligro`, `EstadoPeligro` | — | Agrupar eventos y reportes cercanos en un solo peligro con ciclo nuevo → confirmado → en reparación → reparado |
| `IndiceGeohash` (ampliado) | Tabla hash | Agrupar eventos por celda: O(n) promedio vs. O(n²) comparando todos contra todos |
| `BitacoraFechas` | `TreeMap` (árbol rojo-negro) | Eventos entre dos fechas en O(log n + m) |
| `MonticuloMax` (otra prioridad) | Heap | Ranking de reparación: severidad × tránsito × reincidencia × antigüedad |

La complejidad de lo implementado está en `dashboard-java/README.md`.
