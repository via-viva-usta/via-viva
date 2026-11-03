# report/ — Informe final (IEEE, inglés, 2 columnas)

`main.tex` parte de la propuesta (`docs/propuesta/main.tex`) y describe el sistema **como quedó implementado**
(ESP32 normal, detector por umbrales, maniobras, int8, plan B, bot, mapa web, tablero).

## Reglas

- **No se inventan resultados.** Lo que falta medir está marcado con `\pendiente{...}`, que sale en **rojo** en el PDF
  (19 marcas hoy). Cada una se reemplaza con un número calculado por el repositorio, nunca con una estimación.
- Las cifras de datos (tramos, nodos, km, pendiente, lluvia, barrios) **no se escriben a mano**: vienen de macros
  (`\NTramos`, `\NNodos`, ...) que genera `figuras/generar.py` desde la base.
- Las tablas de E1–E4 y corriente (`tablas/*.tex`) las genera `analysis/experimentos.py`; si no existen, el informe
  muestra la marca `[PENDIENTE]` en su lugar (macro `\incluirsiexiste`).

## Regenerar figuras y tablas

```powershell
analysis\.venv\Scripts\python report\figuras\generar.py      # mapa de Tunja, pendiente, lluvia y macros de datos
analysis\.venv\Scripts\python analysis\experimentos.py        # tablas de E1–E4 (cuando haya exp_*.csv reales)
```

## Compilar

Necesita una distribución de LaTeX con `IEEEtran` (incluida en MiKTeX y TeX Live) y BibTeX:

```powershell
cd report
pdflatex main
bibtex main
pdflatex main
pdflatex main
```

O subir la carpeta `report/` completa a Overleaf (plantilla vacía, compilador pdfLaTeX).

## Estado (2-nov-2026)

**No se ha compilado**: en este PC no hay LaTeX instalado y la descarga de un motor (Tectonic) fue bloqueada por los
permisos de la sesión de Claude Code. Se hizo una revisión estática: llaves y entornos balanceados, las 23 citas
existen en `referencias.bib`, las figuras existen, las macros de datos están definidas y todos los `\ref` tienen
`\label`. Al compilar por primera vez, revisar avisos de cajas desbordadas (`Overfull \hbox`) en las tablas.
