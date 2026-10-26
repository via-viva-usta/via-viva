# Clases UML del tablero Java (propuesta)

Proyecto NetBeans *Java with Ant*, Java 21, Swing. Lee la base SQLite con JDBC (`sqlite-jdbc` en `lib/`).
Las estructuras de datos del curso se implementan a mano (no se usan `PriorityQueue` ni grafos de librerías)
para poder analizar su complejidad; `HashMap` y `TreeMap` de Java se usan donde el curso lo permite.

```mermaid
classDiagram
    direction LR

    class TableroApp {
        +main(String[] args)$
    }
    class VentanaPrincipal {
        -PanelMapa panelMapa
        -PanelRanking panelRanking
        -PanelFiltros panelFiltros
        -PanelDetalle panelDetalle
        +VentanaPrincipal(ControladorTablero c)
    }
    class ControladorTablero {
        -RepositorioSQLite repo
        -GrafoCalles grafo
        -IndiceGeohash indice
        -ColaPrioridadReparacion cola
        -BitacoraFechas bitacora
        +cargarTodo()
        +filtrarPorFechas(LocalDateTime desde, LocalDateTime hasta) List~Evento~
        +topReparaciones(int k) List~Peligro~
        +ordenDeTrabajo(Peligro p) List~Peligro~
    }

    class RepositorioSQLite {
        -String rutaDb
        +leerTramos() List~Tramo~
        +leerEventos() List~Evento~
        +leerReportes() List~Reporte~
        +leerRiesgo(String modelo) Map~Integer, Double~
        +actualizarEstado(int idReporte, EstadoPeligro e)
    }

    class Tramo {
        -int idTramo
        -long osmU
        -long osmV
        -String nombre
        -String tipoVia
        -double longitudM
        -double latCentro
        -double lonCentro
        -double riesgo
    }
    class Evento {
        -int idEvento
        -LocalDateTime tsUtc
        -double lat
        -double lon
        -ClaseEvento clase
        -double severidad
        -double confianza
        -int idTramo
        -String geohash7
    }
    class Reporte {
        -int idReporte
        -LocalDateTime tsUtc
        -double lat
        -double lon
        -String tipo
        -EstadoPeligro estado
        -int idTramo
    }
    class Peligro {
        -String geohash7
        -int idTramo
        -List~Evento~ eventos
        -List~Reporte~ reportes
        -EstadoPeligro estado
        +severidadMax() double
        +reincidencia() int
        +antiguedadDias() long
        +prioridad() double
    }
    class ClaseEvento {
        <<enumeration>>
        HUECO
        RESALTO
        IMPACTO_FUERTE
        NORMAL
        OBSTACULO
    }
    class EstadoPeligro {
        <<enumeration>>
        NUEVO
        CONFIRMADO
        EN_REPARACION
        REPARADO
        DESCARTADO
    }

    class GrafoCalles {
        -Map~Long, List~Arista~~ adyacencia
        +agregarTramo(Tramo t)
        +bfs(long origen, int maxSaltos) List~Long~
        +dfs(long origen) List~Long~
        +corredor(Peligro p, double maxMetros) List~Tramo~
    }
    class Arista {
        -long destino
        -Tramo tramo
    }
    class IndiceGeohash {
        -HashMap~String, Peligro~ celdas
        +insertar(Evento e)
        +insertar(Reporte r)
        +vecinos(String geohash7) List~Peligro~
        +peligros() Collection~Peligro~
    }
    class Geohash {
        +codificar(double lat, double lon, int precision)$ String
    }
    class ColaPrioridadReparacion {
        -Peligro[] heap
        -int tamano
        +insertar(Peligro p)
        +extraerMax() Peligro
        +verMax() Peligro
        -subir(int i)
        -bajar(int i)
    }
    class BitacoraFechas {
        -TreeMap~LocalDateTime, List~Evento~~ arbol
        +agregar(Evento e)
        +rango(LocalDateTime desde, LocalDateTime hasta) List~Evento~
    }

    class PanelMapa {
        +paintComponent(Graphics g)
        -dibujarTramos(Graphics2D g)
        -dibujarPeligros(Graphics2D g)
    }
    class PanelRanking {
        -JTable tabla
        +mostrar(List~Peligro~ top)
    }
    class PanelFiltros
    class PanelDetalle {
        +mostrar(Peligro p)
    }

    TableroApp ..> VentanaPrincipal : crea
    TableroApp ..> ControladorTablero : crea
    VentanaPrincipal --> ControladorTablero
    VentanaPrincipal *-- PanelMapa
    VentanaPrincipal *-- PanelRanking
    VentanaPrincipal *-- PanelFiltros
    VentanaPrincipal *-- PanelDetalle
    ControladorTablero --> RepositorioSQLite
    ControladorTablero *-- GrafoCalles
    ControladorTablero *-- IndiceGeohash
    ControladorTablero *-- ColaPrioridadReparacion
    ControladorTablero *-- BitacoraFechas
    GrafoCalles *-- Arista
    Arista --> Tramo
    IndiceGeohash ..> Geohash
    IndiceGeohash o-- Peligro
    Peligro o-- Evento
    Peligro o-- Reporte
    Peligro --> EstadoPeligro
    Evento --> ClaseEvento
    Reporte --> EstadoPeligro
    ColaPrioridadReparacion o-- Peligro
    BitacoraFechas o-- Evento
    RepositorioSQLite ..> Tramo
    RepositorioSQLite ..> Evento
    RepositorioSQLite ..> Reporte
    JPanel <|-- PanelMapa
    JPanel <|-- PanelRanking
    JPanel <|-- PanelFiltros
    JPanel <|-- PanelDetalle
    JFrame <|-- VentanaPrincipal
```

## Complejidad esperada (para el informe de Estructuras de Datos)

| Operación | Estructura | Complejidad |
|---|---|---|
| Agrupar n eventos en peligros | `IndiceGeohash` (tabla hash) | O(n) promedio vs. O(n²) por fuerza bruta |
| Peligros del mismo corredor | `GrafoCalles.bfs` / `dfs` | O(V + E) |
| Top-k de reparación | `ColaPrioridadReparacion` (heap binario) | O(n) construir + O(k log n) |
| Eventos entre dos fechas | `BitacoraFechas` (`TreeMap`, árbol rojo-negro) | O(log n + m) |

Prioridad de reparación (diseño, sección 8): `severidad × tránsito × reincidencia × antigüedad`.
