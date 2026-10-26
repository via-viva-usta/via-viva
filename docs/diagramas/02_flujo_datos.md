# Flujo de datos (ETL)

```mermaid
flowchart LR
    subgraph EXTRAER["1 · Extraer"]
        N["Nodo<br/>eventos (CSV en microSD / Wi-Fi)"]
        P["phyphox<br/>recorridos de prueba (CSV)"]
        T["Bot de Telegram<br/>reporte + foto + ubicación"]
        I["IDEAM · datos.gov.co<br/>lluvia diaria (API)"]
        R["Noticias / RSS<br/>cierres, accidentes"]
        O["OpenStreetMap<br/>osmnx"]
        A["Alcaldía / Tránsito<br/>inventario, siniestros<br/>(oficio, NO se publica)"]
    end

    subgraph TRANSFORMAR["2 · Transformar"]
        L["Limpieza<br/>tipos, rangos, horas a UTC"]
        G["Geocodificación<br/>texto → lat/lon"]
        M["Ajuste a la calle<br/>punto → tramo más cercano"]
        D["Deduplicación<br/>tabla hash por geohash7"]
        F["Variables por tramo<br/>pendiente, lluvia, huecos cercanos,<br/>accidentalidad, rugosidad"]
    end

    subgraph CARGAR["3 · Cargar"]
        DB[("SQLite")]
    end

    subgraph USAR["4 · Usar"]
        RM["Modelo de riesgo<br/>→ tabla riesgo"]
        TB["Tablero Java"]
        MP["Mapa público"]
    end

    N --> L
    P --> L
    T --> L
    I --> L
    R --> G
    A --> L
    O --> M
    L --> M
    G --> M
    M --> D
    D --> DB
    DB --> F
    F --> RM
    RM --> DB
    DB --> TB
    DB --> MP
```

## Reglas que el flujo hace cumplir

| Paso | Regla |
|---|---|
| Extraer (nodo) | Solo eventos; nunca la trayectoria completa del carro |
| Extraer (bot) | El `chat_id` se guarda como hash con sal, no en claro |
| Extraer (web) | Solo fuentes que permiten acceso automatizado (`robots.txt`), con espera entre peticiones |
| Extraer (Alcaldía) | Se guarda en `data/alcaldia/` (ignorada por Git) |
| Transformar | Horas en UTC; coordenadas WGS84 |
| Deduplicar | Eventos y reportes en la misma celda geohash7 (~153 m) y ventana de tiempo → un solo peligro |
| Cargar | `hash_contenido` único en `fuentes_externas`; `(id_nodo, ts_utc)` único en `eventos` |

## Estado actual

| Pieza | Estado |
|---|---|
| OpenStreetMap → `tramos` | Hecho (`etl/osm_tunja.py`) |
| IDEAM → `fuentes_externas` | Hecho (`etl/scraping/clima_ideam.py`) |
| Noticias → `fuentes_externas` | Plantilla (`etl/scraping/noticias.py`) |
| phyphox → análisis | Fase 3 (`analysis/`) |
| Nodo, bot, ajuste a la calle, deduplicación, variables por tramo | Pendiente |
