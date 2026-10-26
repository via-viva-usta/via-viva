# Modelo entidad-relación

Corresponde a `db/schema.sql`. El tramo de calle (OpenStreetMap) es la unidad que une todo.
`nodos`, `barrios` y `variables_tramo` se agregaron en la Fase 4 (modelo de riesgo).

```mermaid
erDiagram
    TRAMOS ||--o{ EVENTOS : "se asigna a"
    TRAMOS ||--o{ REPORTES : "se asigna a"
    TRAMOS ||--o{ FUENTES_EXTERNAS : "se asigna a (opcional)"
    TRAMOS ||--o{ RIESGO : "recibe"
    NODOS ||--o{ TRAMOS : "osm_u / osm_v"
    TRAMOS ||--|| VARIABLES_TRAMO : "describe"
    BARRIOS ||--o{ VARIABLES_TRAMO : "agrupa (validación espacial)"

    NODOS {
        int osm_id PK
        real lat
        real lon
        int grado
        real elevacion_m
        text fuente_elev
    }

    BARRIOS {
        int id_barrio PK
        text nombre
        text sector
        int es_vereda
        real lat
        real lon
        text fuente
    }

    VARIABLES_TRAMO {
        int id_tramo PK
        text tipo_via
        text clase_superficie
        real longitud_m
        real pendiente_pct
        real lluvia_30d_mm
        real lluvia_max_dia_mm
        int huecos_vecinos
        int accidentes_cercanos
        real rugosidad_media
        real profundidad_max_mm
        text barrio
        text sector
        int etiqueta "1, 0 o NULL"
        text fuente_etiqueta
    }

    TRAMOS {
        int id_tramo PK
        int osm_u "nodo OSM inicial"
        int osm_v "nodo OSM final"
        int osm_key
        text nombre
        text tipo_via "highway"
        text superficie "surface"
        real longitud_m
        real pendiente_pct
        text barrio
        real lat_centro
        real lon_centro
        text geohash7
        text geometria_wkt
    }

    EVENTOS {
        int id_evento PK
        text id_nodo
        text hash_vehiculo
        text ts_utc
        real lat
        real lon
        real velocidad_kmh
        text clase "hueco, resalto, impacto_fuerte, normal, obstaculo"
        real severidad
        real confianza
        real rugosidad
        real profundidad_mm
        text etiqueta_manual
        text foto_ruta "difuminada"
        int id_tramo FK
        text geohash7
    }

    REPORTES {
        int id_reporte PK
        text canal "telegram, web, sms"
        text hash_usuario
        text ts_utc
        real lat
        real lon
        text tipo
        text descripcion
        text foto_ruta "difuminada"
        text estado "nuevo, confirmado, en_reparacion, reparado, descartado"
        int id_tramo FK
        text geohash7
    }

    FUENTES_EXTERNAS {
        int id_fuente PK
        text fuente
        text tipo "clima, cierre_vial, accidente, obra, otro"
        text url
        text titulo
        text variable
        real valor
        text unidad
        text ts_dato
        real lat
        real lon
        int id_tramo FK
        text extra_json
        text hash_contenido UK
    }

    RIESGO {
        int id_riesgo PK
        int id_tramo FK
        text modelo "logistica, bosque"
        text version_modelo
        text fecha_calculo
        real probabilidad
        int rango
        int reportado
        text variables_json
    }
```

**Nota de diseño.** El ciclo de vida del peligro (nuevo → confirmado → en reparación → reparado) está hoy en `reportes.estado`.
Cuando el ETL agrupe eventos y reportes por geohash, conviene una tabla `peligros` (un registro por grupo) con su propio estado;
se agrega cuando exista la deduplicación.
