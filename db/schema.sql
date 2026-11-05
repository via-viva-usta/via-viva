-- =====================================================================
-- VÍA VIVA — Esquema de la base de datos (SQLite 3)
-- =====================================================================
-- Tablas principales:
--   tramos            tramos de calle de OpenStreetMap (unidad del modelo de riesgo)
--   eventos           eventos detectados por el nodo a bordo (NO trayectorias)
--   reportes          reportes ciudadanos (bot de Telegram, web, SMS)
--   fuentes_externas  datos de fuentes públicas (clima IDEAM, noticias de cierres y accidentes)
--   riesgo            probabilidad de hueco no reportado por tramo, por modelo y fecha
-- Tablas de apoyo (Fase 4):
--   nodos             intersecciones del grafo OSM con su elevación (para pendiente y para el tablero)
--   barrios           barrios y veredas de Tunja (datos abiertos de la Alcaldía) para la validación espacial
--   variables_tramo   tabla de variables del modelo de riesgo, una fila por tramo
--
-- Convenciones:
--   * Horas en UTC, texto ISO 8601 ('2026-10-26T14:05:00Z').
--   * Coordenadas WGS84 (EPSG:4326) en grados decimales.
--   * geohash de precisión 7 (celda de ~153 m x 153 m) para agrupar puntos cercanos
--     con una tabla hash en vez de comparar todos contra todos.
--   * Privacidad (Ley 1581 de 2012): nunca se guardan trayectorias completas, ni chat_id
--     de Telegram en claro, ni fotos sin difuminar.
--
-- Uso:  sqlite3 data/via_viva.db < db/schema.sql
--       (o python -m etl.db, que aplica este archivo)
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- tramos: una arista no dirigida del grafo de calles de OSM (osmnx).
-- Una calle de doble sentido es UN tramo (u, v, key) con u < v no garantizado:
-- se guarda tal como lo entrega osmnx al convertir el grafo a no dirigido.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tramos (
    id_tramo        INTEGER PRIMARY KEY AUTOINCREMENT,
    osm_u           INTEGER NOT NULL,          -- id OSM del nodo inicial
    osm_v           INTEGER NOT NULL,          -- id OSM del nodo final
    osm_key         INTEGER NOT NULL DEFAULT 0,-- distingue aristas paralelas entre u y v
    osm_way_ids     TEXT,                      -- id(s) de la vía OSM, separados por ';'
    nombre          TEXT,                      -- nombre de la calle (puede ser NULL)
    tipo_via        TEXT,                      -- etiqueta highway: primary, residential, ...
    superficie      TEXT,                      -- etiqueta surface: asphalt, unpaved, ... (NULL si OSM no la tiene)
    carriles        TEXT,                      -- etiqueta lanes
    vel_max         TEXT,                      -- etiqueta maxspeed
    un_sentido      INTEGER,                   -- 1 si oneway en OSM, 0 si no
    longitud_m      REAL NOT NULL,             -- longitud calculada por osmnx (m)
    pendiente_pct   REAL,                      -- se llena luego con un modelo de elevación público
    barrio          TEXT,                      -- se llena luego (zona piloto / validación espacial)
    lat_centro      REAL NOT NULL,             -- punto medio de la geometría
    lon_centro      REAL NOT NULL,
    geohash7        TEXT NOT NULL,             -- geohash del punto medio
    geometria_wkt   TEXT NOT NULL,             -- LINESTRING en WKT (EPSG:4326)
    fuente          TEXT NOT NULL DEFAULT 'OpenStreetMap (ODbL)',
    fecha_carga     TEXT NOT NULL,             -- UTC
    UNIQUE (osm_u, osm_v, osm_key)
);
CREATE INDEX IF NOT EXISTS idx_tramos_geohash ON tramos (geohash7);
CREATE INDEX IF NOT EXISTS idx_tramos_tipo    ON tramos (tipo_via);

-- ---------------------------------------------------------------------
-- eventos: lo que detecta el nodo (hueco, resalto, impacto fuerte, ...).
-- Solo el evento; la trayectoria del carro NO se guarda.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS eventos (
    id_evento       INTEGER PRIMARY KEY AUTOINCREMENT,
    id_nodo         TEXT NOT NULL,             -- identificador del nodo (p. ej. 'nodo-01')
    hash_vehiculo   TEXT,                      -- hash del vehículo (no la placa)
    ts_utc          TEXT NOT NULL,             -- hora UTC del GPS, interpolada al instante del evento
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    error_pos_m     REAL,                      -- error estimado de posición (HDOP, interpolación)
    velocidad_kmh   REAL,
    clase           TEXT NOT NULL
                    CHECK (clase IN ('hueco', 'resalto', 'impacto_fuerte', 'normal', 'obstaculo',
                                     'giro_izquierda', 'giro_derecha', 'frenada_brusca')),  -- maniobras (MPU-6050)
    severidad       REAL CHECK (severidad BETWEEN 0 AND 1),
    confianza       REAL CHECK (confianza BETWEEN 0 AND 1),
    rugosidad       REAL,                      -- índice de rugosidad de la ventana (acelerómetro)
    profundidad_mm  REAL,                      -- profundidad estimada con el VL53L0X
    etiqueta_manual TEXT,                      -- etiqueta del pulsador (verdad de campo), si la hay
    origen          TEXT NOT NULL DEFAULT 'nodo'  -- nodo (umbral/modelo), phyphox o simulado
                    CHECK (origen IN ('nodo', 'phyphox', 'simulado')),
    razon_umbral    REAL,                      -- p2p / vibración de fondo en el disparo del detector
    foto_ruta       TEXT,                      -- foto asociada al evento, YA difuminada (sin uso desde que salió la ESP32-CAM)
    modelo_version  TEXT,                      -- versión del clasificador del nodo
    id_tramo        INTEGER REFERENCES tramos (id_tramo),  -- tramo asignado por el ETL (ajuste a la calle)
    geohash7        TEXT,
    ts_carga        TEXT NOT NULL,             -- cuándo entró a la base (latencia reporte→mapa)
    UNIQUE (id_nodo, ts_utc)                   -- evita cargar dos veces el mismo evento
);
CREATE INDEX IF NOT EXISTS idx_eventos_tramo   ON eventos (id_tramo);
CREATE INDEX IF NOT EXISTS idx_eventos_geohash ON eventos (geohash7);
CREATE INDEX IF NOT EXISTS idx_eventos_ts      ON eventos (ts_utc);

-- ---------------------------------------------------------------------
-- reportes: canal ciudadano. El ciclo de vida del peligro vive aquí:
-- nuevo → confirmado → en_reparacion → reparado (o descartado).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reportes (
    id_reporte      INTEGER PRIMARY KEY AUTOINCREMENT,
    canal           TEXT NOT NULL CHECK (canal IN ('telegram', 'web', 'sms')),
    hash_usuario    TEXT,                      -- hash con sal del chat_id / teléfono (nunca en claro)
    ts_utc          TEXT NOT NULL,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    tipo            TEXT NOT NULL
                    CHECK (tipo IN ('hueco', 'resalto', 'obstaculo', 'vehiculo_varado', 'otro')),
    descripcion     TEXT,
    foto_ruta       TEXT,                      -- foto difuminada
    estado          TEXT NOT NULL DEFAULT 'nuevo'
                    CHECK (estado IN ('nuevo', 'confirmado', 'en_reparacion', 'reparado', 'descartado')),
    ts_estado       TEXT,                      -- última vez que cambió el estado
    id_tramo        INTEGER REFERENCES tramos (id_tramo),
    geohash7        TEXT,
    ts_carga        TEXT NOT NULL,
    clase_sugerida  TEXT,                      -- clase que sugirió la CNN de fotos (dataset/clasificar.py); la decide una persona
    confianza_sugerida REAL,                   -- probabilidad de esa clase (0-1)
    modelo_sugerencia TEXT                     -- versión del modelo (termina en -SINTETICO si es de prueba)
);
CREATE INDEX IF NOT EXISTS idx_reportes_tramo   ON reportes (id_tramo);
CREATE INDEX IF NOT EXISTS idx_reportes_geohash ON reportes (geohash7);
CREATE INDEX IF NOT EXISTS idx_reportes_estado  ON reportes (estado);

-- ---------------------------------------------------------------------
-- fuentes_externas: todo lo que llega por scraping o APIs públicas.
-- Una fila = un dato (p. ej. lluvia diaria de una estación, o una noticia).
-- hash_contenido evita duplicados al volver a correr el scraper.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fuentes_externas (
    id_fuente       INTEGER PRIMARY KEY AUTOINCREMENT,
    fuente          TEXT NOT NULL,             -- p. ej. 'IDEAM (datos.gov.co s54a-sgyg)'
    tipo            TEXT NOT NULL
                    CHECK (tipo IN ('clima', 'cierre_vial', 'accidente', 'obra', 'otro')),
    url             TEXT NOT NULL,             -- de dónde salió (trazabilidad)
    titulo          TEXT,                      -- título de la noticia o nombre de la estación
    contenido       TEXT,                      -- resumen / texto relevante
    variable        TEXT,                      -- para datos numéricos: 'precipitacion_diaria_mm', ...
    valor           REAL,
    unidad          TEXT,
    ts_dato         TEXT,                      -- fecha a la que se refiere el dato (UTC o fecha local)
    ts_captura      TEXT NOT NULL,             -- cuándo se descargó
    lat             REAL,                      -- ubicación si se conoce (estación, lugar de la noticia)
    lon             REAL,
    id_tramo        INTEGER REFERENCES tramos (id_tramo),
    extra_json      TEXT,                      -- campos originales útiles, en JSON
    hash_contenido  TEXT NOT NULL UNIQUE       -- sha256 de los campos que identifican el dato
);
CREATE INDEX IF NOT EXISTS idx_fuentes_tipo_ts ON fuentes_externas (tipo, ts_dato);

-- ---------------------------------------------------------------------
-- riesgo: salida del modelo predictivo, una fila por tramo, modelo y corrida.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS riesgo (
    id_riesgo       INTEGER PRIMARY KEY AUTOINCREMENT,
    id_tramo        INTEGER NOT NULL REFERENCES tramos (id_tramo),
    modelo          TEXT NOT NULL CHECK (modelo IN ('logistica', 'bosque')),
    version_modelo  TEXT NOT NULL,
    fecha_calculo   TEXT NOT NULL,             -- UTC
    probabilidad    REAL NOT NULL CHECK (probabilidad BETWEEN 0 AND 1),
    rango           INTEGER,                   -- posición en el ranking de esa corrida (1 = más riesgo)
    reportado       INTEGER NOT NULL DEFAULT 0,-- 1 si el tramo ya tenía huecos conocidos
    variables_json  TEXT,                      -- variables usadas y su valor (explicabilidad)
    fuente_etiquetas TEXT,                     -- de dónde salieron las etiquetas: alcaldia, planb (recorridos + bot), demo
    UNIQUE (id_tramo, modelo, version_modelo, fecha_calculo)
);
CREATE INDEX IF NOT EXISTS idx_riesgo_corrida ON riesgo (modelo, version_modelo, fecha_calculo, probabilidad DESC);

-- ---------------------------------------------------------------------
-- nodos: vértices del grafo de calles (intersecciones y extremos).
-- osm_u / osm_v de tramos apuntan a osm_id. La elevación sale de un modelo
-- digital de elevación público (SRTM 30 m vía OpenTopoData).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nodos (
    osm_id          INTEGER PRIMARY KEY,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    grado           INTEGER,                   -- calles que llegan al nodo (street_count de osmnx)
    elevacion_m     REAL,
    fuente_elev     TEXT                       -- p. ej. 'OpenTopoData srtm30m'
);

-- ---------------------------------------------------------------------
-- barrios: punto de referencia de cada barrio o vereda (Alcaldía de Tunja,
-- datos abiertos 4ryc-k7fx). Un tramo pertenece al barrio cuyo punto está más cerca.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS barrios (
    id_barrio       INTEGER PRIMARY KEY,       -- id de la fuente
    nombre          TEXT NOT NULL,
    sector          TEXT,
    es_vereda       INTEGER NOT NULL DEFAULT 0,
    lat             REAL NOT NULL,
    lon             REAL NOT NULL,
    fuente          TEXT NOT NULL,
    fecha_carga     TEXT NOT NULL
);

-- ---------------------------------------------------------------------
-- variables_tramo: entrada del modelo de riesgo (risk_model/variables.py).
-- Se recalcula completa cada vez; 'etiqueta' es la verdad conocida:
--   1 = tramo con hueco confirmado, 0 = tramo revisado sin huecos, NULL = no se sabe.
-- Las variables de "vecinos" excluyen el propio tramo para no filtrar la etiqueta.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS variables_tramo (
    id_tramo            INTEGER PRIMARY KEY REFERENCES tramos (id_tramo),
    fecha_calculo       TEXT NOT NULL,
    tipo_via            TEXT,                  -- highway agrupado (primary, secondary, ..., residential, otro)
    clase_superficie    TEXT,                  -- pavimentada / sin_pavimentar / desconocida
    longitud_m          REAL,
    pendiente_pct       REAL,
    lluvia_30d_mm       REAL,                  -- interpolada (IDW) desde estaciones IDEAM
    lluvia_max_dia_mm   REAL,
    huecos_vecinos      INTEGER,               -- huecos conocidos a <= 300 m en OTROS tramos
    accidentes_cercanos INTEGER,               -- siniestros a <= 200 m
    rugosidad_media     REAL,                  -- medida por el nodo en el tramo (NULL si no pasó)
    profundidad_max_mm  REAL,
    barrio              TEXT,
    sector              TEXT,
    distancia_barrio_m  REAL,                  -- distancia al punto del barrio asignado
    etiqueta            INTEGER CHECK (etiqueta IN (0, 1)),
    fuente_etiqueta     TEXT
);
CREATE INDEX IF NOT EXISTS idx_variables_barrio ON variables_tramo (barrio);
