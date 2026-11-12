# viaviva/ — la aplicación de VÍA VIVA

Misma base de código en el PC (con phyphox) y en la Raspberry Pi 4 (con sensores). Arquitectura: `docs/ARQUITECTURA.md`.
Salida de campo paso a paso: `README_SALIDA.md`.

## Instalar

- **PC (Windows):** `powershell -ExecutionPolicy Bypass -File viaviva\instalar_pc.ps1` → `viaviva\.venv`.
  Se usa con `viaviva.cmd …` desde la carpeta `via-viva` (o doble clic en `SALIDA_DE_CAMPO.cmd`).
- **Mac** (sin probar en Mac): `bash viaviva/instalar_mac.sh` → `./viaviva.sh …`. **Docker** (plan B, solo captura del
  PC, sin probar): `Dockerfile` + `docker-compose.yml` en la raíz. Pasos para un PC ajeno: `README_SALIDA.md`.
- Práctica sin datos de campo en cualquier PC: `capture --replay ejemplo --por-http` y `doctor --simulado ejemplo`
  (recorrido SINTÉTICO). `.env` opcional: `VIAVIVA_PIN` (PIN fijo de `/marcar`), `VIAVIVA_IP_PC` e
  `VIAVIVA_IPS_EDITOR` (solo Docker).
- **Raspberry Pi 4** (OS Lite 64 bits, manual de armado v3): `bash viaviva/instalar.sh` → servicio `via-viva-pi`
  (graba desde el arranque; el pulsador de GPIO27 apaga limpio). **Sin probar en hardware.**

## Comandos

| Comando | Para qué |
|---|---|
| `viaviva doctor [--source pi] [--url …] [--simulado <export>]` | Pre-chequeo: LISTO o FALTA X (código de salida 0/1) |
| `viaviva capture` | Captura con phyphox (`http://172.20.10.1`, puerto 80 u 8080 autodetectado) + tablero en `:8000`; graba sola |
| `viaviva capture --replay <export> [--por-http] [--velocidad 5] [--bucle]` | Reproduce una salida como si fuera en vivo |
| `viaviva capture --source pi --puerto 80 --permitir-apagado` | En la Pi (lo usa el servicio) |
| `viaviva serve` | Solo el tablero local |
| `viaviva resumen <sesión o export>` | RESUMEN.md |
| `viaviva detector detectar\|evaluar\|calibrar <sesiones…>` | Detector calibrable (`config/detector.yaml`) |
| `viaviva dataset construir <sesiones…>` · `viaviva dataset evaluar <manifest>` | Dataset de ventanas y clasificador por salida |
| `viaviva modelo <manifest>` (en `vv-modelo`) | Esqueleto TFLite int8 (etapa siguiente) |
| `viaviva usuarios crear <u> --rol editor\|alcaldia\|docente` | Usuarios del tablero local (la clave se escribe en la consola) |
| `viaviva sync --una-vez` · `viaviva nube preparar` | Sincronización con Supabase · sitio en línea (`docs/NUBE.md`) |
| `viaviva r7 medir\|consumo\|tabla` | Informe de recursos (`docs/R7.md`) |

## Páginas del tablero local (`http://<equipo>:8000`)

| Página | Quién | Qué |
|---|---|---|
| `/captura` | equipo (editor) | Grabar, marcar (1–7, U), señal, GPS, sensores, PIN para el celular, apagar (Pi) |
| `/marcar` | celular del copiloto (PIN de la consola) | Botones grandes 1–7 y deshacer, sin zoom |
| `/sync` | quien filma | Reloj UTC grande y destello de 3 s (queda guardado en la sesión) |
| `/sesiones` | equipo | Salidas con resumen, calidad, recorrido, video y avance de revisión |
| `/revision?s=<sesión>` | equipo | Importar el video (se sincroniza solo), línea de tiempo con señal + video, confirmar / corregir / descartar. Si el video es HEVC o el navegador no lo reproduce, avisa y ofrece «Convertir a H.264» cuando `ffmpeg` está instalado (opcional; `winget install Gyan.FFmpeg` en Windows, `sudo apt install ffmpeg` en la Pi); el original se conserva |
| `/dataset` | equipo | Construir el dataset, ver balance y cobertura, evaluar umbrales y clasificador |
| `/demo` | equipo (proyector) | Recorrido guiado de 2 min: captura → detección → mapa → reporte |
| `/tablero` | editor, Alcaldía, docentes | Huecos por estado y riesgo por tramo, prioridad, exportar PDF/CSV/Excel, importar reparaciones |

## Pines (Raspberry Pi 4, BCM, manual v3)

ADXL345 #1 SPI0 CE0 (GPIO8) + INT1 GPIO17 · ADXL345 #2 CE1 (GPIO7, opcional) · I2C1 GPIO2/3: MPU-6050 0x68, VL53L0X
0x29, BH1750 0x23 · GPS `/dev/serial0` 9600 · DHT22 GPIO4 · pulsador GPIO27 (`gpio-shutdown`) · LED GPIO22.
Cada sensor es opcional: si falta, la captura arranca y lo informa (`viaviva doctor --source pi`).
