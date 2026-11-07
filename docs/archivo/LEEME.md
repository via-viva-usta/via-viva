# docs/archivo — lo obsoleto (movido, no borrado)

Ordenado el **7-nov-2026**. Nada se borró: lo versionado se movió con `git mv` (el historial lo conserva) y lo local
quedó en `local_sin_git/` (ignorada por Git).

## Movido (en Git)

| Antes | Ahora | Por qué |
|---|---|---|
| `docs/propuesta/main.tex`, `referencias.bib` | `docs/archivo/propuesta_ESP32-S3/` | Propuesta entregada con la ESP32-S3 y la ESP32-CAM (descartadas el 2 y 3-nov). Es el documento entregado: **no se modifica** |
| `dashboard-java/docs/captura_demo.png` | `docs/archivo/captura_tablero_2026-11-02.png` | Captura del tablero antes de la pestaña "Reportes y eventos"; la nueva está en `docs/img/` |
| `demo/iniciar.ps1` | `iniciar.ps1` (raíz) | No es obsoleto: pasó a ser el **único** script que levanta todo (con la captura en vivo) |
| `docs/REVISION_TECNICA_2026-11-07.md` | `docs/archivo/REVISION_TECNICA_2026-11-07.md` | Revisión técnica del 7-nov ya aplicada (extracción segura del ZIP y DMA de 8 bytes validados) |

## Movido (local, sin Git: `docs/archivo/local_sin_git/`)

| Antes | Ahora | Por qué |
|---|---|---|
| `report/main.pdf` | `local_sin_git/report_main.pdf` | PDF del informe del 3-nov: viejo; el informe ahora vive en Overleaf |
| `cache/er.json`, `cache/mermaid_test.html`, `cache/tablero.png` | `local_sin_git/cache_*` | Salidas sueltas de pruebas de diagramas y capturas viejas |

## Quitado (temporales que se regeneran solos)

`report/main.aux`, `.bbl`, `.blg`, `.log`, `.out` (salidas de LaTeX) y `.pytest_cache/`. No había `__pycache__` fuera de
los venvs.

## Se queda donde está (no es obsoleto)

- `futuro/` (ESP32-CAM, láser de cuadrícula, OBD2): es **trabajo futuro**, no archivo.
- `docs/03_VIA_VIVA_desarrollo.md`: diseño vigente con las notas de los cambios del 2 y 3-nov.
- `report/`: base del informe (el texto nuevo va en `docs/cambios_informe.md` para Overleaf).
- `firmware/`, `dataset/` y `tests/`: no se tocaron.
