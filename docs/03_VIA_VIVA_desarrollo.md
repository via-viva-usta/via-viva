# Proyecto Integrador 2026-2 — 03 · VÍA VIVA (desarrollo)

Fecha: 2026-10-13 · Carpeta: PROYECTO INTEGRADOR · Línea temática: **Movilidad**
Propuesta propia del equipo, independiente de las propuestas anteriores.
Compra asociada: `02_COMPRAS\VIA_VIVA_Cotizacion.xlsx` (hoja «ELEGIDA - 1 nodo»).
Equipo (4): Andrés Santiago Cárdenas González, Juan Felipe García Carvajal, Juan Diego Anzola Duarte, Dany Alexander Cipamocha Riaño.

> **Actualización 2-nov-2026 — cambio de placa.** La placa principal pasa a ser la **ESP32 normal (WROOM-32, DevKit de 30 pines)**: sin PSRAM, sin instrucciones vectoriales y con pines distintos (ver `CLAUDE.md`, sección 5). E2 queda como flash vs. SRAM y E3 como float32 vs. int8. Presupuesto aproximado: **330.000 COP**. La ESP32-CAM se programa con un adaptador CP2102. La atención al ciudadano es un bot de Telegram + un mapa web estático, sin backend. El resto del diseño se mantiene.

## 1. Idea en una frase

Nodos con IA en el borde, a bordo de vehículos, detectan huecos, resaltos e impactos en las vías de Tunja. Una cámara documenta cada evento con evidencia anonimizada (foto difuminada, hora y GPS). Todo alimenta un mapa vivo, junto con reportes ciudadanos y fuentes públicas, para la autoridad (tablero) y la ciudadanía (mapa público).

## 2. Decisiones de enfoque (13-oct)

| Tema | Decisión |
|---|---|
| Papel de la cámara | **Reporte con evidencia** para la autoridad; **no multa** |
| Dónde va el dispositivo | **A bordo de vehículos** (se mueve por la ciudad) |
| Usuario principal | **Autoridad (tablero) + mapa público** |
| Hardware de visión | **ESP32-CAM** (detección simple y difuminado en el borde) |
| Vehículo de pruebas | **Sí, el equipo tiene carro para pruebas** |
| Prototipo | **1 nodo** (ESP32 WROOM-32 de sensores + ESP32-CAM; antes ESP32-S3, cambio del 2-nov), con acelerómetro de repuesto y sensor láser VL53L0X (decisiones 20 y 24-oct) |
| Capa predictiva | **Mapa de riesgo georreferenciado** de huecos no reportados (sugerencia del docente y comité curricular, 24-oct) |
| Presupuesto | ≈ **330.000 COP** (actualizado 2-nov con la ESP32 normal; antes 342.400); cargador, cable y soporte los pone el equipo |
| Tiempo | **4 semanas**: 19 oct – 13 nov 2026 |
| Gestión institucional | Alcaldía por oficio vía contacto en Infraestructura (Sr. Hermen Román Díaz); Gobernación por derecho de petición (VUV). Living Lab va aparte del integrador |

## 3. Contexto y diferenciación

- **El proceso actual es manual.** Dos informes de pasantía de Ingeniería Civil USTA en la Secretaría de Infraestructura de Tunja (2022) describen formatos de campo e inspección manual de patologías de la vía.
- **Tunja ya tiene fotomultas.** Desde el 16-mar-2026 hay cámaras fijas en la Av. Norte (calles 59, 53 y 41), la Av. Oriental con carrera 7 y la BTS (Amparo del Niño). Detectan velocidad, semáforo en rojo, SOAT y revisión técnico-mecánica. Las opera el Consorcio de Tránsito Tunja, con una concesión de unos 35.000 millones COP a 25 años (Infobae, 5-feb-2026).
  - Por eso VÍA VIVA **no compite en multas**. Una fotomulta exige equipos autorizados bajo la Ley 1843 de 2017.
  - VÍA VIVA cubre lo que las cámaras fijas no ven: estado de la vía, obstáculos y vehículos varados o mal parqueados en carril, en movimiento por toda la ciudad. El consorcio puede ser cliente, no competencia.
- **Antecedente: Street Bump (Boston).** Tuvo falsos positivos en su primera versión, poca adopción ciudadana (en 2014, unos 16.000 de 19.000 reportes vinieron de empleados de la ciudad) y fricción de uso.
  - VÍA VIVA responde con un nodo fijo en flota que registra solo, confirmación por varias fuentes y verificación de la reparación.
- **No hay datos locales para entrenar.** RDD2022 (47.420 imágenes de 6 países) no incluye Colombia. Sirve para preentrenar; hay que afinar con imágenes propias.

## 4. Arquitectura del sistema

```
NODO (a bordo)
  ESP32 sensores ── VSPI ──> ADXL345 (FIFO, INT watermark) ──DMA──> buffer A | buffer B
        │          ── I2C ──> MPU-6050 (giroscopio, línea base)
        │          ── UART ─> GPS NEO-6M (posición, velocidad, hora UTC)
        │          ── HSPI ─> microSD (registro crudo)
        │  Núcleo 1: ventana → filtro → características → inferencia int8 → evento
        │  Núcleo 0: cola de eventos → SD → Wi-Fi (hotspot) / store-and-forward
        └── UART ──> ESP32-CAM: "evento en t" → foto → difuminado → miniatura + metadatos

SERVIDOR / PC
  ETL (eventos + reportes ciudadanos + scraping + OSM) → SQLite → tablero Java Swing + mapa público
```

## 5. Adquisición (protagonista)

| Sensor | Qué aporta | Notas de diseño |
|---|---|---|
| ADXL345 (SPI, FIFO de 32 muestras, ±16 g) | Hueco, resalto, rugosidad, impacto | Sensor principal. Probar SPI apenas llegue (algunos clones GY-291 fallan) |
| MPU-6050 (I2C) | Giroscopio + línea base de bus | Experimento E4 (I2C vs SPI) |
| GPS NEO-6M | Posición, velocidad, hora UTC | ~5 Hz máx. (verificar). A 30 km/h: 8,3 m entre fijaciones a 1 Hz; 1,7 m a 5 Hz |
| ESP32-CAM (OV2640) | Evidencia visual del evento | Solo se activa con evento; difuminado de placas y rostros en el borde |
| Pulsador | Etiquetas de campo (ground truth) | Lo oprime el copiloto, nunca el conductor |

Decisiones de señal:
- **Muestreo: se mide, no se supone.** Capturar a tasa alta en las primeras pasadas, calcular la densidad espectral y escoger la fs mínima que conserve el 95 % de la energía. Hipótesis inicial: 200 Hz con filtro antialias en torno a 80 Hz.
- **Sincronía.** Un retraso de 300 ms al sellar la hora equivale a 2,5 m de error a 30 km/h. Usar la hora UTC del GPS e interpolar la posición del evento entre fijaciones.
- **Orientación libre del nodo.** Estimar la gravedad con el vehículo detenido (velocidad GPS = 0) y rotar al eje vertical. Calibración estática de 6 posiciones.
- **Datos.** A 200 Hz el registro crudo genera 3,2 KB/s (≈ 11,5 MB/h). Un evento de 64 B cada 10 s (supuesto) son 6,4 B/s, unas 500 veces menos. Ese es el argumento cuantitativo del borde.

### Protocolo de captura con el carro del equipo
- Ruta piloto fija en Tunja con huecos y resaltos conocidos, fotografiados y georreferenciados a mano como verdad de campo.
- Varias pasadas a 20, 30 y 40 km/h; en seco y, si se puede, en mojado.
- Conductor solo conduce; el copiloto etiqueta con el botón. Nodo bien fijado (velcro y ventosa).
- División entrenamiento/prueba **por recorrido**, no por ventana.

## 6. Arquitectura del computador (protagonista)

- **Dos procesadores por nodo.** El ESP32 de sensores detecta y le pide la foto al ESP32-CAM por UART. Reparto de carga entre procesadores y protocolo entre ellos.
- **Doble núcleo.** Núcleo 1 para adquisición e inferencia; núcleo 0 para SD y comunicaciones.
- **Buses separados.** SPI para el acelerómetro y SPI aparte para la microSD (evita contención). I2C para el MPU-6050, UART para GPS y para la cámara. El I2C del ESP32 no usa DMA.
- **DMA con doble buffer (ping-pong).** La FIFO del ADXL345 avisa cada 32 muestras: a 200 Hz es una interrupción cada 160 ms.
- **A esta tasa el bus no es el cuello de botella.** La ganancia del DMA es liberar la CPU. Hay que medirlo.
- **Memoria.** Una ventana de 2 s en 3 ejes son 2,4 KB. El modelo int8 vive en flash con caché o en SRAM (experimento E2).

| # | Pregunta | Se compara | Métricas |
|---|---|---|---|
| E1 | ¿Cómo adquirir? | Polling vs interrupción por muestra vs FIFO + DMA ping-pong | Jitter, CPU %, muestras perdidas con SD y Wi-Fi activos, mA |
| E2 | ¿Dónde viven los pesos? | Flash con caché vs SRAM | Latencia de inferencia |
| E3 | ¿Cuánto acelera? | float32 vs int8 | Latencia, RAM, Flash, F1 |
| E4 | ¿Qué bus? | I2C (MPU-6050) vs SPI (ADXL345) | Tiempo de lectura, ocupación de CPU |

Mínimo para el informe: E1 y E3.

## 7. Procesamiento

1. Filtro pasa-bajos y retiro de gravedad.
2. Disparo de ventana por energía o jerk.
3. Características normalizadas por velocidad: pico, RMS, curtosis, factor de cresta y energía por banda.
4. Comparación de dos clasificadores: árbol o bosque exportado a C vs CNN 1D int8.
5. Severidad y confianza por evento.
6. **Cámara:** detección simple de obstáculo o vehículo en carril y difuminado. No se promete lectura de placas: requiere más cómputo y va en contra de la privacidad.
7. **Registro del evento:** id, hora UTC, lat, lon, velocidad, clase, severidad, confianza, hash del vehículo y miniatura difuminada.

## 7b. Capa predictiva georreferenciada (24-oct)

El comité curricular consideró el proyecto viable y el docente sugirió agregar **modelos predictivos con georreferencia** y un **sensor de mapeo directo** para estimar dónde hay huecos u obstáculos **aún no reportados**.

- **Mapeo directo:** el acelerómetro mide la **rugosidad** de cada tramo (señal temprana de deterioro) y el **VL53L0X** (láser ToF, I2C, $25.000), apuntando al piso desde el bómper, mide el **perfil y la profundidad** del hueco. Limitación: pierde alcance con sol fuerte; hay que probarlo.
- **Datos por tramo (OSM):** tipo de vía y superficie, pendiente (modelo de elevación público), lluvia (IDEAM), huecos conocidos (nodo, ciudadanos, inventario de la Alcaldía), puntos de accidentalidad (Tránsito) y rugosidad y profundidad medidas.
- **Modelo:** regresión logística y bosque aleatorio (explicables, funcionan con pocos datos), con validación espacial (barrios completos fuera del entrenamiento). Salida: **mapa de calor** y ranking de tramos a revisar.
- **Validación en campo (métrica central):** visitar los 10 tramos de mayor riesgo **no reportados** y 10 al azar y comparar cuántos tienen huecos. Meta secundaria: AUC ≥ 0,70.
- **Zona piloto:** unos pocos barrios, para cubrirlos bien en 3 semanas.
- **Dato clave:** el **inventario de vías de la Alcaldía con ubicación**; pedírselo a Stiven así.

| Etapa | Qué se hace | Cuándo |
|---|---|---|
| 1. Mapa base | Tramos OSM, pendiente, lluvia, scraping, datos de la Alcaldía | 24–30 oct |
| 2. Sensado | Recorridos: rugosidad, profundidad y huecos por tramo | 28 oct – 5 nov |
| 3. Modelo | Unir datos, entrenar, validación espacial | 3–6 nov |
| 4. Validación | Top-10 de riesgo vs. 10 al azar en campo | 6–9 nov |
| 5. Entrega | Mapa de calor en el tablero, informe, póster, pitch | 9–13 nov |

## 8. Estructuras de datos

| Estructura | Uso |
|---|---|
| Búfer circular y cola | Ventanas en el nodo; eventos pendientes de envío |
| Hash sobre rejilla (geohash) | Agrupar eventos cercanos en un solo "peligro" (vs fuerza bruta: análisis de complejidad) |
| Grafo (lista de adyacencia, OSM) | Tramos de calle. BFS/DFS para agrupar peligros del mismo corredor en una orden de trabajo |
| Heap | Ranking de reparación: severidad × tránsito × reincidencia × antigüedad |
| TreeMap (ABB) y bitácora ordenada | Consultas por rango de fechas y búsqueda binaria |
| Java Swing | Tablero para la autoridad: grafo dibujado y marcadores por severidad |

**Ciclo de cada peligro:** nuevo → confirmado → en reparación → reparado. Lo cierran pasadas posteriores sin impacto.

## 9. ETL y web scraping

- **Fuentes:** eventos de los nodos, reportes ciudadanos (bot de Telegram o formulario web), OpenStreetMap y fuentes públicas que permitan scraping (páginas oficiales, RSS, datos abiertos, clima IDEAM).
- **Respetar robots.txt.** Algunos medios locales bloquean bots.
- **Pasos:** limpieza → geocodificación y ajuste a la calle → deduplicación → carga a SQLite → agregados para el tablero y el mapa.

## 10. Métricas

- F1 de huecos.
- Error de posición (m).
- Falsos positivos por km.
- Latencia de inferencia (ms).
- Consumo (mA, medido con el tester USB).
- RAM/Flash usadas.
- Porcentaje de duplicados fusionados.
- Tiempo hasta confirmar un peligro.

## 11. Privacidad y legalidad

- Placas y rostros son datos personales (Ley 1581 de 2012): se difuminan en el nodo y nunca sale la imagen original.
- Se guardan eventos, no trayectorias completas. Consentimiento del conductor de cada vehículo.
- El sistema **no genera comparendos**: entrega evidencia y estadística a la autoridad (Ley 1843 de 2017 regula la fotodetección).

## 12. Modelo comercial

- En el semestre no se firma un contrato público. Meta realista:
  - Reto **Living Lab** con la Gobernación de Boyacá.
  - Carta de intención o piloto con la Secretaría de Infraestructura o de Tránsito de Tunja.
- Después: contratación por SECOP II, con suscripción a la plataforma y kits para flotas.
- Otros clientes: el operador de fotodetección, transportadoras y flotas municipales.

## 13. Parte visual y publicitaria

- **Nombre.** VÍA VIVA es nombre de trabajo; consultar la base de marcas de la SIC y los dominios antes de fijarlo. Alternativas: Pulso Vial, Tunja Pulse, BacheMap.
- **Concepto.** "El pulso de la calle": la línea de la vía como electrocardiograma que cae en cada hueco.
- **Eslogan.** EN: *Every pothole, on the map.* · ES: *Las calles de Tunja, en tiempo real.*
- **Identidad.** Gris asfalto, amarillo señal y verde azulado para "reparado". Severidad codificada con forma y color, para que sea legible con daltonismo.
- **Piezas:**
  - Tablero (vistas de ciudadano, operador y demo).
  - Póster.
  - Pitch de 3–5 min en inglés: problema → solución → demo → resultados → negocio.
  - Video de respaldo de menos de 5 min.
  - README de GitHub y publicación en LinkedIn.
  - Etiqueta del nodo.

## 14. Alcance por niveles

1. **Nivel 1 (obligatorio):** nodo con acelerómetro, GPS y SD que clasifica huecos y resaltos; mapa en vivo; ETL con deduplicación; métricas.
2. **Nivel 2:** cámara con evidencia difuminada, canal ciudadano, scraping, confianza entre fuentes, ciclo de reparación y ranking con heap.
3. **Nivel 3 (si sobra tiempo):** envío por LoRa, alerta de impacto fuerte y antena GPS activa.

## 15. Plan de 4 semanas

| Semana | Foco |
|---|---|
| 1 (19–23 oct) | Compra, cartas firmadas y entregadas, puesta en marcha de acelerómetro + GPS + SD |
| 2 (26–30 oct) | Recorridos con el carro y etiquetas; análisis espectral (define fs); árbol de referencia; E1 |
| 3 (3–6 nov) | Modelo int8 en el nodo (E2, E3); cámara si alcanza; ETL, grafo OSM, tablero Swing, bot ciudadano |
| 4 (9–13 nov) | Pruebas de campo finales, métricas, informe, póster, video y pitch |

Áreas de trabajo (una por integrante; todos apoyan recorridos y pitch):
- (A) Hardware y firmware — Arquitectura
- (B) Señales e IA — SADP
- (C) Datos y plataforma: ETL, scraping, estructuras, tablero, bot — Estructuras de Datos
- (D) Gestión, documento y pitch: entidades, docentes, informe IEEE, póster, video, compras

## 16. Tareas de esta semana

- [x] ~~Confirmar la ESP32-S3~~ → se usa ESP32 normal (2-nov).
- [ ] Hacer la compra según `VIA_VIVA_Cotizacion.xlsx` y asignar responsables.
- [ ] Derecho de petición a Tránsito de Tunja: siniestros georreferenciados 2024–2025.
- [ ] Derecho de petición a la Secretaría de Infraestructura: inventario de huecos y formato de inspección.
- [ ] Contacto con Infraestructura vía Ingeniería Civil USTA; explorar el reto Living Lab con la Gobernación.
- [ ] Definir la ruta piloto y fotografiar sus huecos y resaltos.

## Fuentes

- Infobae (5-feb-2026), cámaras de fotodetección en Tunja: https://www.infobae.com/colombia/2026/02/05/tunja-activara-camaras-de-fotodeteccion-en-avenidas-y-rutas-clave-controles-electronicos-funcionaran-las-24-horas-desde-el-16-de-marzo/
- Ley 1843 de 2017 (Rama Judicial): https://sidn.ramajudicial.gov.co/SIDN/NORMATIVA/TEXTOS_COMPLETOS/7_LEYES/LEYES%202017%20(1822-)/LEY%201843%20DE%202017%20(REGULA%20LOS%20SISTEMAS%20AUTOM%C3%81TICOS%20Y%20LOS%20MEDIOS%20TECNOL%C3%93GICOS%20PARA%20EL%20CONTROL%20DEL%20TR%C3%81FICO).PDF
- RDD2022 (arXiv): https://arxiv.org/abs/2209.08538v1
- Street Bump (Harvard D3): https://d3.harvard.edu/platform-digit/submission/street-bump-crowdsourcing-better-streets-but-many-roadblocks-remain/
- Informe de práctica, Secretaría de Infraestructura de Tunja (USTA, 2022): https://repository.usta.edu.co/items/87b16f56-0138-4234-ab02-e6da83b6f925/full
- Pasantía en la Secretaría de Infraestructura de Tunja (USTA, 2022): https://repository.usta.edu.co/bitstreams/3f85e77b-eb81-4ffd-a3fc-11c11f6bf6a1/download
- ESP32 (Espressif): https://www.espressif.com/en/products/socs/esp32
