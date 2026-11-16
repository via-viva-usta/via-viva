# CLAUDE.md — VÍA VIVA (lo que hay que saber para trabajar aquí)

Actualizado el **13-nov-2026**. Primero lee este archivo, luego `GUIA_TRABAJO.md` (ramas y quién edita qué) y, según la
tarea, `viaviva/README.md`, `README_SALIDA.md` o `docs/`. El historial largo (decisiones viejas, ESTADO, informe) salió
del repo el 13-nov: sigue en Git y en `02_VIA_VIVA/_archivo/repo_2026-11-13/` del PC de AC.

## 1. Qué es
Proyecto Integrador 2026-2 (Ingeniería de Datos e IA, USTA Tunja). Detecta y mapea huecos, resaltos e impactos en Tunja y
estima el riesgo por tramo. **Prototipo:** Raspberry Pi 4 con ADXL345 + GPS (o iPhone con phyphox en las salidas de
prueba) → detector por umbrales → app local (`viaviva/`, FastAPI, SQLite = fuente de verdad) → sincronización opcional a
Supabase → tablero web (`web/en_linea/`, Netlify). No genera multas ni lee placas.

## 2. Tres carriles (13-nov)
| Carril | Regla |
|---|---|
| **Campo** | Versión de la prueba en el carro **congelada** en la etiqueta `campo-2026-11-13` (se crea solo cuando AC avise que pasó la prueba real con el iPhone A). Clon aparte `C:\VIA_VIVA_CAMPO`, sin cambios ni funciones nuevas. El botón **Actualizar** se bloquea solo fuera de `main` (`viaviva/actualizacion.py`, prueba en `tests/test_actualizacion.py`) |
| **Software** | App, motor, Pi y firmware: ramas cortas `ac/<tarea>` → PR → `main`; los clones en `main` se ponen al día con **Actualizar** |
| **Web** | Dany, en `web/`: ramas `dani/<tarea>` → PR (vista previa de Netlify) → `main` → publicado |
El formato de sesión debe seguir siendo legible por versiones posteriores (`nucleo.py`, `sesiones.py`, `resumen.py`).

## 3. Reglas
1. **Ramas y PR:** `main` protegida (checks `pytest`, `node-test`, `compilar` + 1 aprobación de otra persona). Nunca
   empujar a `main`, `push --force` ni reescribir historial. Antes de borrar una rama sin fusionar: etiqueta `archivo/<rama>`.
   Claude no fusiona PR ni contacta colaboradores por su cuenta: eso lo hace AC.
2. **Responsables:** Dany → `web/` (no cambiar su interfaz). AC → `viaviva/`, `firmware/`, `db/`, `tests/`. No tocar
   sensores, Pi, servicio ni firmware sin tarea explícita; no mezclarlos con cambios visuales.
3. **Estilos:** `web/en_linea/marca.css` es la única fuente de tokens (`--m-*`, `--t-*`, `--vv-*`) de la web y la app.
   `web/en_linea/estilo.css` y `viaviva/web/estilo.css` son composiciones distintas: no copiar una sobre otra.
4. **Secretos:** solo en `.env` (ignorado). Nunca pedir ni mostrar claves en el chat. El sitio en línea recibe
   `SUPABASE_URL` y `SUPABASE_CLAVE_PUBLICA` como variables de Netlify (`herramientas/config_web.mjs`).
5. **Datos:** nunca en Git `06_CAMPO`, `data/raw/`, `data/alcaldia/`, `*.db`, fotos, videos ni `data/certificados/`.
6. **Verdad:** todo número sale de código o medición; lo sintético se marca SINTÉTICO/DEMO; decir qué no se probó en
   hardware real (hoy: la Pi, el iPhone por HTTPS, Mac).
7. **Idioma y commits:** español sencillo; commits pequeños con prefijo (`feat(viaviva): …`, `docs: …`) y la línea
   `Co-Authored-By` cuando los hace Claude. Lo obsoleto se mueve fuera del repo; no se borran archivos locales de AC.
8. **Alcance:** fuera del prototipo (13-nov): bot de Telegram, reportes ciudadanos tipo Waze y `futuro/`. El scraping
   (clima IDEAM y noticias, `etl/scraping/`) se queda: es requisito del curso y alimenta el riesgo; en la Pi es opcional
   (`instalar.sh --con-scraping`). `risk_model/` y `dataset/` se quedan. Pendientes de Dany: la pestaña de reportes del
   tablero y `web/clasificador/`. `dashboard-java/`: queda el código; el `.jar` se baja aparte.

## 4. Mapa del repo
`viaviva/` app (captura `phyphox | pi | replay`, `doctor`, detector, dataset, FastAPI, `app` = ventana propia,
`actualizacion.py`, `conexion.py`, `camara.py`, instaladores `instalar_pc.ps1` / `instalar_mac.sh` / `instalar.sh`,
`sistemas/`, `r7/`) · `web/en_linea/` sitio de Dany · `firmware/` ESP32 (histórico) · `db/` esquema y `acceso.py` ·
`config/` detector y experimento phyphox · `analysis/` detector y señales · `etl/` OSM, geohash, recorridos, scraping ·
`risk_model/` · `dataset/` fotos y CNN · `dashboard-java/` · `herramientas/` (`tarea.cmd`/`.sh`, `buscar_secretos.py`,
`validar_campo.py`, `config_web.mjs`) · `tests/` (pytest; `tests/web` con Node) · `docs/` técnico.

## 5. Comandos
- App: `viaviva.cmd app | doctor | capture [--replay ejemplo --por-http] | serve | resumen | detector | dataset | usuarios
  | sync | nube | r7` (Mac/Linux: `./viaviva.sh`). Icono VÍA VIVA = `viaviva app`.
- Pruebas: `dataset\.venv\Scripts\python -m pytest` y `… -m ruff check .`; web: `node --test tests/web/*.test.mjs`.
- Secretos: `dataset\.venv\Scripts\python herramientas\buscar_secretos.py`.

## 5b. Entorno (PC de AC, Windows 11)
Python 3.11 (`py -3.11`). Venvs: `viaviva\.venv` (app), `dataset\.venv` (pruebas: pytest, ruff, httpx, OpenCV < 5),
`etl\.venv` (ETL y riesgo), `analysis\.venv`, `%USERPROFILE%\.venvs\vv-modelo` (TensorFlow). PlatformIO:
`%USERPROFILE%\.platformio\penv\Scripts\pio.exe`. GitHub: organización `via-viva-usta`, repo **público** `via-viva`;
cuenta correcta `andresscardens` (`GH_TOKEN=$(gh auth token --user andresscardens) gh …`).

**Trampas:** en Bash, los heredoc con `\\` se dañan (escribir scripts con Write en el scratchpad); la consola imprime mal
UTF-8 (`PYTHONIOENCODING=utf-8`); `.cmd` con CRLF; Overpass da 502/504 (hay caché); `ruta.parent.parent/06_CAMPO`: un clon
dentro de `02_VIA_VIVA` graba sesiones en el `06_CAMPO` real (probar en carpetas temporales o con `--salida`).

## 6. Pines del nodo ESP32 (histórico; lo cita `firmware/nodo-sensores/README.md`)
WROOM-32, 4 MB flash, 520 KB SRAM. Fuente única: `firmware/nodo-sensores/include/pines.h`.
ADXL345 SCK/MISO/MOSI/CS 18/19/23/4 (VSPI + DMA), INT1 34 · microSD 14/27/13/32 (HSPI por matriz GPIO) · I2C SDA/SCL
21/22 (MPU-6050 0x68, VL53L0X 0x29, BH1750 0x23) · GPS UART2 16/17 · DHT22 25 · pulsador 26 · LED 33.
Pines de la Raspberry Pi (BCM, manual v3): `viaviva/config.py` y `viaviva/README.md`.

## 7. Equipo
| Persona | GitHub | Área |
|---|---|---|
| Andrés Cárdenas (AC) | `andresscardens` (admin) | Software, datos, coordinación; opera Claude Code |
| Dany Cipamocha | `dany286-ri` | Interfaz web (`web/`), hardware |
| Juan Felipe García («Pipe») | `juanfelipegarciacarvajal444-rgb` | Señales e IA; en campo, iPhone B (video) |
| Juan Diego Anzola | `Juandi-1` | Informe (Overleaf), póster, pitch; en campo, iPhone A (phyphox) y Lenovo de captura |
