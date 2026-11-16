# VÍA VIVA

Detecta y mapea huecos, resaltos e impactos en las vías de Tunja (Boyacá, Colombia) y estima el riesgo por tramo de
calle. Prototipo: **Raspberry Pi 4 con ADXL345 + GPS** (o un iPhone con phyphox) → detección en el carro → **app
local** → sincronización opcional a **Supabase** → **tablero web** para la Alcaldía.
Proyecto Integrador 2026-2 · Ingeniería de Datos e IA · Universidad Santo Tomás, Seccional Tunja. **No** genera multas
ni lee placas.

## Empezar

| Quiero… | Abra |
|---|---|
| Trabajar en el repo (ramas, PR, quién edita qué) | [`GUIA_TRABAJO.md`](GUIA_TRABAJO.md) |
| Hacer una salida de campo | [`README_SALIDA.md`](README_SALIDA.md) |
| Ver todos los comandos de la app | [`viaviva/README.md`](viaviva/README.md) |
| Entender la arquitectura y los datos | [`docs/`](docs/README.md) |

Instalar la app en Windows (una vez, con internet; deja el icono **VÍA VIVA** en el escritorio):

```powershell
git clone https://github.com/via-viva-usta/via-viva.git
cd via-viva
powershell -ExecutionPolicy Bypass -File viaviva\instalar_pc.ps1
```

Mac: `bash viaviva/instalar_mac.sh` (sin probar en Mac). Raspberry Pi: `bash viaviva/instalar.sh` (sin probar en
hardware). Practicar sin carro: en la app, **Conexión → Usar el ejemplo** (recorrido SINTÉTICO por Tunja).

## Qué hay

| Carpeta | Qué es |
|---|---|
| `viaviva/` | La app: captura (phyphox, Pi o reproducción), detector, tablero local, sincronización, instaladores |
| `web/en_linea/` | Sitio público (portada + tablero), publicado con Netlify (`netlify.toml`) |
| `firmware/` | Nodo ESP32 (histórico, fuera del prototipo desde el 9-nov; la CI lo sigue compilando) |
| `db/`, `config/` | Esquema SQLite y ajustes (detector, experimento de phyphox) |
| `analysis/`, `etl/`, `risk_model/`, `dataset/` | Señales y detector, calles OSM y scraping, modelo de riesgo, fotos y CNN |
| `dashboard-java/` | Tablero Java (Estructuras de Datos); el `.jar` se baja aparte (ver su README) |
| `tests/`, `.github/` | Pruebas y CI: `pytest` (+ ruff), `node-test` y `compilar` son obligatorias para entrar a `main` |

Nunca en Git: `.env`, claves, datos de campo (`06_CAMPO`), fotos ni videos. Todo dato sintético se marca SINTÉTICO/DEMO.

Licencias de datos: OpenStreetMap (ODbL), barrios de la Alcaldía (datos abiertos), IDEAM vía datos.gov.co (CC BY-SA 4.0).
