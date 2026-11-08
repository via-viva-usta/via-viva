# pi/ — Raspberry Pi 4 como nodo central (desde el 7-nov-2026)

El docente de Arquitectura consideró insuficiente el ESP32 como nodo central. Desde el 7-nov la **Raspberry Pi 4
Model B** lee los sensores, detecta, guarda en SQLite, sirve el aplicativo web y sincroniza con la nube cuando hay
internet. El ESP32 queda **solo como línea base de R7** y como argumento de Arquitectura (`justificacion.md`).

> Todo lo de hardware está **[VALIDAR EN PLACA]**: se escribió y probó en el PC (pruebas `tests/test_pi.py` y modo
> reproducir). Pines **pendientes de confirmar con la rama de Dany** (`config.py`).

## Cómo encaja

```
 sensores (SPI, I2C, UART, GPIO) ─┐
                                  ├─► Nucleo ─► detector por umbrales ─► eventos ─► SQLite (fuente de verdad)
 grabación de phyphox / de la Pi ─┘     │            (igual al del ESP32)            │   huecos (≤ 10 m) y estados
       (modo reproducir: demo)          └─► grabación en formato phyphox             ├─► tablero / exportables
                                                                                     └─► cola ─► Supabase (opcional)
 celular o tablet (WiFi VIA-VIVA) ─► http://192.168.4.1  captura  ·  /tablero  tablero en vivo
```

| Archivo | Qué hace |
|---|---|
| `config.py` | Pines BCM, tasas, rutas; parámetros del detector (iguales a `analysis/detector_umbral.py`) |
| `sensores.py` | ADXL345 por SPI con **FIFO + interrupción en GPIO** (sustituye al DMA), MPU-6050, VL53L0X, BH1750, GPS NMEA, DHT22 tolerante a fallos |
| `fuentes.py` | Hilos de adquisición (ADXL con prioridad de tiempo real, I2C a 100 Hz, GPS, ambiente, pulsador y LED) y **modo reproducir** |
| `nucleo.py` | Detector muestra a muestra, grabación en formato phyphox (+ ambiente, distancia, eventos, etiquetas), Welford |
| `estructuras.py` | Búfer circular, cola, tabla hash, montículo, grafo con BFS e índice geohash, escritos a mano (ver Big-O abajo) |
| `almacen.py` | SQLite: eventos, **huecos** (agrupación ≤ 10 m, detectado → verificado → reparado / descartado, historial), riesgo, orden de atención |
| `usuarios.py` | Roles y sesiones (contraseñas PBKDF2 creadas en la consola) |
| `exportar.py` | PDF top-10 con mapa, Excel de 3 hojas, CSV; **importar reparaciones** por CSV con validación |
| `sincronizacion.py` + `supabase_esquema.sql` | Cola con reintentos; solo eventos y riesgo, lista blanca de columnas |
| `sistema.py` | % CPU, temperatura, RAM, bajo voltaje (`vcgencmd`), registro R7 cada 10 s |
| `servidor.py` | Servidor web (biblioteca estándar) y apagado seguro |
| `web/` | `captura.html` (celular o tablet fija, botones grandes), `tablero.html` (en vivo), `entrar.html` |
| `instalar.sh`, `sistemas/` | Instalación en la Pi y servicios systemd |
| `r7/` | `benchmark_cnn.py` (CNN int8 en la Pi) y `tabla_r7.py` (tabla Pi vs. ESP32 vs. celular) |

## Instalación en la Pi (una vez, con internet)

1. Raspberry Pi OS Bookworm 64 bits en la microSD; usuario normal; clonar el repo en `~/via-viva`.
2. `bash pi/instalar.sh` → paquetes, SPI/I2C/UART, venv, Leaflet local, WiFi **VIA-VIVA** (192.168.4.1), permiso de
   apagado, servicios. La clave del WiFi va en `.env` (`PI_AP_CLAVE`) o se escribe en la consola.
3. Copiar `data/via_viva.db` del PC (calles de OSM y riesgo) y crear los usuarios:
   `pi/.venv/bin/python -m pi.usuarios crear andres --rol editor --nombre "Andrés Cárdenas"` (cada quien escribe su clave).
4. `sudo reboot`. El servicio `via-viva-pi` arranca solo.

## Uso

| Quién | Dónde | Qué |
|---|---|---|
| Copiloto (editor) | celular o tablet fija → WiFi VIA-VIVA → `http://192.168.4.1` | Iniciar/detener grabación, etiquetar con botones grandes, ver señal, GPS y sensores, apagar |
| Equipo (editor) | `/tablero` | Cambiar estado de huecos y reportes, importar reparaciones (CSV), exportar |
| Alcaldía, docentes | `/tablero` | Solo lectura: mapa de dos capas (huecos y riesgo por tramo), top-10, orden de atención, exportar PDF/Excel/CSV |

- **Pulsador:** corto = marca rápida ("otro", se corrige en la web); **sostenido 3 s = apagado seguro** (cierra la
  grabación con fsync y apaga; protege la microSD). LED: fijo = listo, lento = grabando, rápido = falla de sensor.
- **Alimentación:** toma de 12 V del carro → adaptador USB-C **5 V / 3 A**. La página avisa si hay bajo voltaje.
- **Sin internet todo funciona.** Para sincronizar: cable de red o USB al celular con datos (la WiFi de la Pi es el
  punto de acceso). Sin `SUPABASE_URL`/`SUPABASE_CLAVE` en `.env`, nada sale de la Pi.
- **Demo sin carro** (Pi o PC): `python -m pi.servidor --fuente reproducir --archivo data/raw/phyphox/2026-11-07_03_pipe.zip --bucle`
  (en el PC: `.\iniciar.ps1 -Reproducir ...`). Los eventos quedan `origen='simulado'` y nunca entran al modelo ni a la nube.
- **Grabaciones:** `data/raw/pi/AAAA-MM-DD_HHMMSS_nombre/` en formato phyphox → sirven sin cambios para
  `herramientas.validar_campo`, `etl.recorridos`, `analysis/` y el modo reproducir. Fuera de Git.

## Roles

| Rol | Puede |
|---|---|
| `editor` (4: el equipo) | Todo: captura, estados, importar, exportar |
| `alcaldia` | Ver el tablero y exportar |
| `docente` | Ver el tablero y exportar |

Sin usuarios creados, el aplicativo solo responde a la misma máquina (127.0.0.1), como editor: sirve para la demo
en el PC. Sesión de 30 días en cookie `HttpOnly; SameSite=Strict`; 5 intentos fallidos bloquean 5 min la IP.
Pendiente: HTTPS (hoy la red WiFi WPA2 protege el tráfico).

## Estructuras de datos y costo (Estructuras de Datos)

| Estructura | Uso | Costo |
|---|---|---|
| Búfer circular | Últimas 600 muestras (gráfica), ventana pico a pico, eventos y etiquetas recientes | O(1) por muestra, memoria fija |
| Cola (índice de cabeza) | Frontera del BFS | O(1) amortizado |
| Tabla hash (encadenamiento, carga ≤ 0,75) | Tramos por id, conteo de peligros por tramo, celdas geohash | O(1) promedio |
| Montículo máximo | Top-10 de riesgo entre 5 775 tramos; orden de atención | construir O(n), top-k O(n + k log n) |
| Grafo de calles + BFS | Corredor a ≤ 2 intersecciones; zonas de riesgo conectadas | O(V + E) |
| Índice geohash-7 | Ajustar un evento a su calle sin internet; agrupar detecciones en huecos | O(1) + candidatos (9 celdas) |

## R7 en la Pi (frente al ESP32)

El servicio deja cada 10 s una línea en `data/logs/r7_pi.jsonl`: latencia del detector por muestra, de vaciar la FIFO,
de INT1 → lectura y del ciclo I2C (media ± desviación, Welford), % de CPU, temperatura, RAM y bajo voltaje. Consumo
con el tester USB: `pi/r7/tabla_r7.py consumo ...`. CNN de fotos: `pi/r7/benchmark_cnn.py`.
Tabla final: `pi/r7/tabla_r7.py tabla`. **Resultados: [PENDIENTE: medición en la placa].**

## Pines (propuesta, BCM) — [PENDIENTE: confirmar con la rama de Dany]

| Señal | BCM (físico) | Nota |
|---|---|---|
| ADXL345 SCLK/MISO/MOSI/CS | 11/9/10/8 (23/21/19/24) | SPI0 CE0, modo 3, 1,5 MHz |
| ADXL345 INT1 | 17 (11) | Flanco de subida |
| I2C SDA/SCL | 2/3 (3/5) | MPU-6050 0x68, VL53L0X 0x29, BH1750 0x23; 400 kHz |
| GPS TX → RX de la Pi | 15 (10) | `/dev/serial0`, 9600 baud |
| DHT22 | 4 (7) | Pull-up 10 kΩ a 3V3 |
| Pulsador / LED | 27 (13) / 22 (15) | Pulsador a GND; LED con 330 Ω |
Todo a 3,3 V. Se cambian sin tocar código con `PI_PIN_*` en `.env`. Sin módulo microSD (la Pi usa la suya).
