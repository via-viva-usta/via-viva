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
| `video_<AAAAMMDD_hhmmss>_<id>.mov/.mp4/.m4v` (+ `…_h264.mp4` si se convirtió), `video.json` | archivo, metodo (destello / fecha_del_archivo / manual), desfase_s, cobertura_pct, codec, avisos, conversion, original | Video del iPhone B importado desde la app (cada carga conserva las anteriores; `video.json` apunta a la vigente; máx. 8 GiB); `desfase_s` = segundo de la sesión en que empieza el video. La conversión a H.264 (ffmpeg) deja el original al lado |
| `sesion.sqlite` · tabla `revision` | t_s, decision (confirmar / corregir / descartar), clase, usuario, utc | Decisiones de la pantalla Revisión; descartar = `via_buena` |
| `RESUMEN.md`, `resumen.json` | | Al cerrar: duración, muestras, pérdidas, km, velocidad máx., minuto quieto, marcas por clase |
| `Accelerometer_mpu6050.csv`, `Accelerometer_adxl2.csv`, `Distancia_vl53l0x.csv`, `Ambiente.csv` | | Solo en la Pi |

Clases de marca (teclas 1–7): `hueco, resalto, grieta, parche, tapa, obstaculo, via_buena`. Retardo de reacción −1,0 s.

**Identificación de equipos (desde el 19-nov).** La bitácora agrega:
- en `inicio`, la `fuente`: rol `nodo_pi` / `phyphox_referencia` / `reproduccion` y alias tomado de
  `VIAVIVA_ALIAS_FUENTE`, o `desconocido`;
- en `inicio`, el `equipo`: sistema operativo, versión, arquitectura y Python, sin nombre del equipo;
- `dispositivo`: rol, alias y navegador/SO corto de cada celular o PC que se identificó en `/marcar`, `/camara` o `/sync`;
- `estado_fuente` cada minuto: fs efectiva, desfase del reloj de la fuente, pérdidas y conexión.

Los alias son del equipo de trabajo (`PHONE-A`, `CAMARA-1`), nunca nombres de personas. Sin alias registrado, la
identidad física es `desconocido`.

**Sesión real del 18-nov (`sesion_2026-11-18_0619`), con celulares y phyphox, no con la Pi.** Qué dice la evidencia:
- **Datos inerciales y GPS:** `origen: phyphox`, `id_nodo: phyphox-pc`. Coinciden muestra a muestra con el export
  crudo del iPhone A (180 628 de 180 629).
- **Video:** `origen_video: celular`, sincronizado a mano (`metodo: manual`, 8,154 s). No hubo destellos.
- **Qué no quedó registrado:** qué celular, navegador o persona usó cada página. Por eso no se puede atribuir identidad
  física a ningún equipo.
- **Hora:** `ts_utc` y `utc` quedaron +2 108,9 s adelantados (corregido para las próximas sesiones en el PR #56).
- **Marcas:** 1 de 69 revisada con video.

## 1b. Dataset de sesiones reales (`herramientas/ingestar_sesion.py`, fuera de Git)

`python -m herramientas.ingestar_sesion agregar <sesión>` copia la sesión, sin el video, a
`C:\VIA_VIVA_DATOS\dataset_vv\sesiones\`. También guarda en `meta\<sesión>\`:
- la procedencia, con el SHA-256 de cada archivo;
- la auditoría;
- las correcciones de hora, documentadas **sin aplicarlas**.

Rechaza las sesiones de reproducción o SINTÉTICAS. `apto_entrenamiento` sigue falso mientras falte algo:
- sincronía del video por destello;
- marcas revisadas con video;
- alias de los equipos;
- auditoría sin FALLA.

`… aptas` lista las rutas que puede leer `viaviva dataset construir`. La sesión del 18-nov ya está ingestada como
**no apta**, con sus 4 motivos.

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
