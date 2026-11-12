#!/usr/bin/env bash
# VÍA VIVA en Mac o Linux: "./viaviva.sh doctor", "./viaviva.sh capture --abrir", "./viaviva.sh capture --replay ejemplo".
# Equivale a viaviva.cmd de Windows. Usa viaviva/.venv (lo crea viaviva/instalar_mac.sh). [SIN PROBAR EN MAC]
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")" && pwd)"
PY="$RAIZ/viaviva/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "No hay entorno de Python. Ejecute primero:  bash viaviva/instalar_mac.sh" >&2
  exit 2
fi
cd "$RAIZ"
export PYTHONIOENCODING=utf-8
exec "$PY" -m viaviva "$@"
