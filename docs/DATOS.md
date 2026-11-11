# Datos de VÍA VIVA: sesión, base, dataset y nube

Nada de esto va al repositorio: las sesiones viven en `02_VIA_VIVA/06_CAMPO/sesiones/` (y el Drive restringido), la base
en `data/*.db`, los derivados en `data/procesado/`. Solo el código y las muestras sintéticas de las pruebas están en Git.

## 1. Sesión de captura (`sesion_AAAA-MM-DD_hhmm[_nombre]/`)

| Archivo | Columnas | Nota |
|---|---|---|
| `Accelerometer.csv` | Time (s), X/Y/Z (m/s²), UTC PC (s) | Mismo formato del export de phyphox iOS + hora UTC del PC por muestra |
| `Gyroscope.csv` | Time (s), X/Y/Z (rad/s), UTC PC (s) | |
| `Location.csv` | Time (s), Latitude, Longitude, Height, Velocity (m/s), Direction, Horizontal Accuracy (m), Vertical Accuracy, UTC PC (s) | |
| `meta/time.csv` | event, experiment time, system time, text | `START` = epoch de t = 0 |
| `etiquetas.csv` | id, t_s, utc, hora_local, clase, lat, lon, vel_kmh, origen, retardo_s, anula_id | Todas las marcas; una fila `deshacer` anula otra |
| `../<carpeta>_etiquetas.csv` | t_s, clase | Solo las vigentes (lo que leen `etl.recorridos`, el detector y el dataset) |
| `eventos.csv` | t_s, ts_utc, p2p_g, razon, lat, lon, vel_kmh, id_tramo, clase, severidad, confianza | Disparos del detector en vivo |
| `destellos.csv` | t_s, utc, hora_local, origen, nota | Instantes de sincronía con el video |
| `bitacora.jsonl` | utc, tipo, … | inicio, corte, reconexion, perdida, etiqueta, deshacer, destello, aviso, fin (con latencias) |
| `sesion.sqlite` | etiquetas, eventos, destellos | Confirmadas al instante (a prueba de cierres bruscos) |
| `video_<AAAAMMDD_hhmmss>_<id>.mov/.mp4/.m4v`, `video.json` | archivo, metodo (destello / fecha_del_archivo / manual), desfase_s, cobertura_pct, avisos | Video del iPhone B importado desde la app (cada carga conserva las anteriores; `video.json` apunta a la vigente; máx. 8 GiB); `desfase_s` = segundo de la sesión en que empieza el video |
| `sesion.sqlite` · tabla `revision` | t_s, decision (confirmar / corregir / descartar), clase, usuario, utc | Decisiones de la pantalla Revisión; descartar = `via_buena` |
| `RESUMEN.md`, `resumen.json` | | Al cerrar: duración, muestras, pérdidas, km, velocidad máx., minuto quieto, marcas por clase |
| `Accelerometer_mpu6050.csv`, `Accelerometer_adxl2.csv`, `Distancia_vl53l0x.csv`, `Ambiente.csv` | | Solo en la Pi |

Clases de marca (teclas 1–7): `hueco, resalto, grieta, parche, tapa, obstaculo, via_buena`. Retardo de reacción −1,0 s.

## 2. Base SQLite (`db/schema.sql`, 14 tablas)

`tramos` (OSM), `nodos`, `barrios`, `variables_tramo`, `riesgo`, `fuentes_externas` (scraping), `reportes`,
`eventos` (+ `id_hueco`, `severidad` 0–1: baja 0,2 · media 0,5 · alta 0,9), **`huecos`** (detecciones ≤ 10 m; estado
detectado → verificado → reparado / descartado; `severidad` texto; `simulado`), `cambios_estado` (historial: quién,
cuándo, web o CSV), `usuarios` (hash PBKDF2), `sesiones` (hash del token), `cola_envio` y `sync_marcas` (outbox).
Migraciones automáticas en `db/acceso.py` (`COLUMNAS_NUEVAS` y la cola que ahora acepta huecos).

## 3. Dataset de ventanas (`viaviva dataset construir`)

`manifest.csv`: sesion, ventana, t0_s, t1_s, utc_centro, lat, lon, **etiqueta** (marca a ± 1,5 s del centro o
`sin_marca`), **estado** (`ok`, `quieto` < 2 km/h, `hueco_datos` > 10 % interpolado) y características: `rms_v, pico_v,
p2p_v, curtosis_v, cresta_v, jerk_max, e_0_2hz, e_2_5hz, e_5_10hz, e_10_20hz, e_20_50hz, rms_h, vel_kmh`.
Ventanas de 2 s con 50 % de solape a 100 Hz; eje vertical = proyección sobre la gravedad (`viaviva/senal.py`).
`calidad.md` (por sesión y por clase, desbalance) y `fotos_asociadas.csv` (foto ↔ ventana a ≤ 30 m y ± 10 min).
Evaluación siempre **dejando una salida completa afuera** (sin fugas).

## 4. Nube (Supabase, `viaviva/supabase_esquema.sql`)

`eventos_publicos`, `huecos_publicos` (con estado y severidad), `riesgo_publico` (+ vista `riesgo_ultimo`),
`cambios_remotos` (pedidos de los editores), `perfiles` (rol). Lista blanca de columnas en `viaviva/sincronizacion.py`;
coordenadas a 5 decimales; nada simulado ni DEMO.

## 5. Licencias de fuentes

OpenStreetMap (ODbL) · barrios de la Alcaldía en datos abiertos · IDEAM vía datos.gov.co (CC BY-SA 4.0) · SRTM vía
OpenTopoData · noticias: solo titular, enlace y fecha (`docs/SCRAPING.md`) · mapa base OpenFreeMap.
