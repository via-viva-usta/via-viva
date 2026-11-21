#!/usr/bin/env bash
# Actualiza la app de la Raspberry Pi desde main y vuelve al commit anterior si algo falla.
#   bash herramientas/actualizar_pi.sh          (en la Pi, desde la raíz del repo; pide sudo para el servicio)
# Pasos: (1) exige rama main y sin cambios locales, (2) git pull --ff-only, (3) reinstala dependencias solo si
# cambió viaviva/requirements.txt, (4) reinicia via-viva-pi y espera 15 s a que siga activo. Si falla 2, 3 o 4,
# vuelve al commit anterior (git reset --hard al commit guardado: solo en la Pi, nunca se empuja) y reinicia el
# servicio con la versión que funcionaba. NO PROBADO EN HARDWARE REAL todavía (16-nov-2026).
set -uo pipefail
cd "$(dirname "$0")/.."

SERVICIO=via-viva-pi
PY=viaviva/.venv/bin/python
ESPERA_S=15

rama=$(git rev-parse --abbrev-ref HEAD)
if [ "$rama" != main ]; then
  echo "Esta copia está en '$rama', no en main: no se actualiza (el carril de campo queda congelado)." >&2
  exit 1
fi
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "Hay cambios locales en archivos del repo: no se actualiza. Revíselos con: git status" >&2
  exit 1
fi

anterior=$(git rev-parse HEAD)
req_antes=$(git rev-parse HEAD:viaviva/requirements.txt 2>/dev/null || echo ninguno)
echo "Versión actual: $(git log -1 --format='%h %s')"

volver() {
  echo "FALLÓ: $1. Vuelvo a ${anterior:0:7}." >&2
  git reset --hard "$anterior" >/dev/null
  if [ "$(git rev-parse HEAD:viaviva/requirements.txt 2>/dev/null || echo ninguno)" != "$req_nuevo" ]; then
    "$PY" -m pip install -q -r viaviva/requirements.txt || true
  fi
  sudo systemctl restart "$SERVICIO" || true
  echo "Quedó en $(git log -1 --format='%h %s'). Revise: journalctl -u $SERVICIO -n 50" >&2
  exit 1
}

req_nuevo=$req_antes
git pull --ff-only origin main || { echo "No se pudo bajar main (sin internet o historia distinta). No cambió nada." >&2; exit 1; }
nuevo=$(git rev-parse HEAD)
if [ "$nuevo" = "$anterior" ]; then
  echo "Ya estaba al día."
  exit 0
fi
echo "Cambios: $(git rev-list --count "$anterior..$nuevo") commits ($(git log -1 --format='%h %s'))"

req_nuevo=$(git rev-parse HEAD:viaviva/requirements.txt 2>/dev/null || echo ninguno)
if [ "$req_nuevo" != "$req_antes" ]; then
  echo "Cambiaron las dependencias: pip install -r viaviva/requirements.txt"
  "$PY" -m pip install -q -r viaviva/requirements.txt || volver "no se pudieron instalar las dependencias"
fi

"$PY" -c "import viaviva" || volver "la app nueva no carga (import viaviva)"
sudo systemctl restart "$SERVICIO" || volver "systemctl restart $SERVICIO"
sleep "$ESPERA_S"
systemctl is-active --quiet "$SERVICIO" || volver "$SERVICIO no siguió activo $ESPERA_S s después de reiniciar"

echo "Listo: ${anterior:0:7} -> ${nuevo:0:7} y $SERVICIO activo."
