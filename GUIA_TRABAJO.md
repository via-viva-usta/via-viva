# Guía de trabajo — una página

## Tres carriles

| Carril | Qué | Cómo se usa |
|---|---|---|
| **Campo** | Software de la prueba en el carro, **congelado** en la etiqueta `campo-2026-11-13` | Clon aparte `C:\VIA_VIVA_CAMPO`, sin editar ni actualizar (`README_SALIDA.md`) |
| **Software** | App, motor, Pi y firmware | Ramas cortas `ac/<tarea>` → PR → `main`; la app se pone al día con **Actualizar** |
| **Web** | Sitio en línea (`web/en_linea/`) | Ramas cortas `dani/<tarea>` → PR (Netlify muestra una vista previa) → `main` → publicado |

## Qué hay en cada carpeta

| Carpeta | Qué es |
|---|---|
| `viaviva/` | La app: captura, detector, tablero local, sincronización, instaladores (PC, Mac, Pi) |
| `web/en_linea/` | Sitio público de Dany (portada + tablero). `marca.css` = estilos de la web **y** de la app |
| `firmware/` | Nodo ESP32 (histórico; el check `compilar` lo construye) |
| `db/` · `config/` | Esquema SQLite · ajustes del detector y experimento de phyphox |
| `analysis/` · `etl/` · `risk_model/` · `dataset/` | Detector y señales · calles OSM y scraping · modelo de riesgo · fotos y CNN |
| `tests/` | Pruebas (pytest y `tests/web` con Node) |
| `herramientas/` | `tarea.cmd`/`tarea.sh`, `buscar_secretos.py`, `config_web.mjs` (Netlify) y otras |

## Quién edita qué

| Persona | Edita | No toca sin avisar |
|---|---|---|
| Dany | `web/` | `viaviva/`, `firmware/` |
| AC | `viaviva/`, `firmware/`, `db/`, `tests/` | `web/` (la interfaz es de Dany) |
| Los dos | rama `compartida/<tarea>`, avisando antes en el grupo | — |

## Paso a paso (Windows y Mac igual; en Mac use `./herramientas/tarea.sh`)

1. **Una vez:** instalar Git, VS Code, GitHub CLI y Node.js (y Python 3.11 si va a tocar código de Python); luego
   `git clone https://github.com/via-viva-usta/via-viva.git` → `cd via-viva` → `code .`
   - Entorno de pruebas de Python (solo AC o quien toque `.py`; ~2 min, Git lo ignora):
     Windows `py -3.11 -m venv .venv` → `.venv\Scripts\python -m pip install -r tests\requirements.txt`;
     Mac `python3.11 -m venv .venv` → `.venv/bin/python -m pip install -r tests/requirements.txt`
2. **Empezar una tarea** (crea la rama desde `main` al día): `herramientas\tarea.cmd dani/iconos-mapa`
3. **Probar** antes de subir:
   - Web: `node --test tests/web/*.test.mjs`
   - Python: `.venv\Scripts\python -m pytest` y `.venv\Scripts\python -m ruff check .`
     (Mac: `.venv/bin/python …`; en el PC de AC sirve también `dataset\.venv`)
4. **Guardar y subir:** `git add -A` → `git commit -m "feat(web): qué cambió"` → `git push -u origin HEAD` →
   `gh pr create --fill`
5. **Revisión:** otra persona aprueba el PR; AC lo fusiona cuando los 3 checks (`pytest`, `node-test`, `compilar`)
   están en verde. Nadie empuja a `main` directo ni usa `--force`.
6. **Después de fusionar:** `git switch main` → `git pull` → `git branch -d dani/iconos-mapa`

## Reglas cortas

- Una tarea = una rama corta = un PR pequeño. Si una rama tiene más de 3 días, actualícela con `main` o ciérrela.
- Nunca en Git: `.env`, claves, `06_CAMPO`, datos de campo, fotos, videos.
- Lo que sale del repo no se pierde: queda en el historial y en etiquetas `archivo/<rama>`.
