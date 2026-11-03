# Arquitectura del sistema

GitHub y VS Code muestran estos diagramas directamente (Mermaid).

## Vista general

```mermaid
flowchart LR
    subgraph NODO["Nodo a bordo (carro)"]
        direction TB
        subgraph S3["ESP32 WROOM-32 · nodo-sensores"]
            direction TB
            C1["Núcleo 1<br/>adquisición → filtro → características → inferencia int8"]
            C0["Núcleo 0<br/>cola de eventos → microSD → Wi-Fi (store-and-forward)"]
            C1 -- "cola FreeRTOS" --> C0
        end
        ADXL["ADXL345<br/>acelerómetro ±16 g<br/>FIFO 32 muestras"]
        MPU["MPU-6050<br/>giroscopio"]
        TOF["VL53L0X<br/>láser ToF (profundidad)"]
        GPS["GPS NEO-6M<br/>posición, velocidad, hora UTC"]
        SD[("microSD<br/>registro crudo")]
        BTN["Pulsador<br/>etiqueta de campo"]
        CAM["ESP32-CAM · nodo-camara<br/>OV2640 → foto → difuminado"]

        ADXL -- "VSPI + INT1 (GPIO 34)" --> S3
        MPU -- "I2C 0x68" --> S3
        TOF -- "I2C 0x29" --> S3
        GPS -- "UART2 9600 baud" --> S3
        S3 -- "HSPI (matriz GPIO)" --> SD
        BTN -- "GPIO 26" --> S3
        S3 <-- "UART1: FOTO / OK" --> CAM
    end

    subgraph FUENTES["Otras fuentes"]
        BOT["Bot de Telegram<br/>reportes ciudadanos"]
        WEB["Fuentes públicas<br/>IDEAM, noticias (robots.txt)"]
        OSM["OpenStreetMap<br/>grafo de calles (osmnx)"]
    end

    subgraph SERVIDOR["PC / servidor"]
        ETL["ETL (Python)<br/>limpieza → ajuste a la calle → deduplicación (geohash)"]
        DB[("SQLite<br/>tramos · eventos · reportes<br/>fuentes_externas · riesgo")]
        RISK["Modelo de riesgo<br/>logística · bosque aleatorio"]
        DASH["Tablero Java Swing<br/>(autoridad)"]
        MAPA["Mapa público"]
    end

    NODO -- "eventos + miniatura difuminada" --> ETL
    BOT --> ETL
    WEB --> ETL
    OSM --> ETL
    ETL --> DB
    DB <--> RISK
    DB --> DASH
    DB --> MAPA
```

## Reparto de trabajo dentro del ESP32

```mermaid
flowchart TB
    INT["ISR GPIO 34<br/>(watermark FIFO = 31 muestras,<br/>cada 155 ms a 200 Hz)"] -- "notificación" --> TA
    subgraph N1["Núcleo 1 (APP_CPU)"]
        TA["tareaAdquisicion<br/>lee el lote por SPI + DMA"] --> PP["búfer ping-pong<br/>A | B"]
        PP --> TP["tareaProcesamiento<br/>ventana → filtro → características<br/>→ clasificador"]
    end
    subgraph N0["Núcleo 0 (PRO_CPU)"]
        TG["tareaGPS<br/>NMEA → posición + hora UTC"]
        TS["tareaRegistro<br/>microSD (crudo + eventos)"]
        TC["tareaCamara<br/>orden FOTO por UART1"]
        TI["tareaI2C<br/>MPU-6050 + VL53L0X"]
    end
    TP -- "colaEventos" --> TS
    TP -- "colaEventos" --> TC
    TG -. "última posición (mutex)" .-> TP
    TI -. "giro + distancia (mutex)" .-> TP
```

## Protocolo UART entre nodo-sensores y nodo-camara

Texto ASCII, una orden por línea (terminada en salto de línea), 115200 baud.

```mermaid
sequenceDiagram
    participant S as ESP32 (sensores)
    participant C as ESP32-CAM
    S->>C: FOTO,id_evento,ts_utc
    activate C
    C->>C: captura OV2640 (JPEG)
    C->>C: difuminado (pendiente)
    C-->>S: OK,id_evento,bytes
    deactivate C
    Note over S,C: Si falla la cámara responde ERR,id_evento,codigo
    S->>C: PING
    C-->>S: PONG
```
