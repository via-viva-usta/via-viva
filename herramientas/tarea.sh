#!/usr/bin/env bash
# Empieza una tarea en una rama nueva SIEMPRE desde main al día.  Uso:  ./herramientas/tarea.sh dani/iconos-mapa
# Prefijos: ac/ (app, motor, firmware), dani/ (web), compartida/ (los dos, avisando antes). Ver GUIA_TRABAJO.md.
set -euo pipefail
RAMA="${1:-}"
if ! [[ "$RAMA" =~ ^(ac|dani|compartida)/[a-z0-9-]+$ ]]; then
  echo "Uso: ./herramientas/tarea.sh ac/descripcion-corta   (o dani/... o compartida/...; minúsculas, números y guiones)" >&2
  exit 2
fi
cd "$(dirname "$0")/.."
if [ -n "$(git status --porcelain)" ]; then
  echo "Hay cambios sin guardar. Haga commit o descártelos antes de empezar otra tarea." >&2
  exit 1
fi
git switch main
git pull --ff-only origin main
git switch -c "$RAMA"
echo
echo "Lista: rama $RAMA creada desde main al día. Al terminar: git push -u origin HEAD  y  gh pr create --fill"
