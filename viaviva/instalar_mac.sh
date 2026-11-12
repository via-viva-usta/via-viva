#!/usr/bin/env bash
# VÍA VIVA en un Mac (una vez, con internet). [SIN PROBAR EN MAC]
# Uso, desde la carpeta via-viva:   bash viaviva/instalar_mac.sh
# Crea viaviva/.venv con lo mismo que el PC con Windows (captura con phyphox, tablero local, detector, dataset).
# Usa Homebrew (https://brew.sh) para Python 3.11 y, opcional, ffmpeg. No pide ni guarda claves.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"

# Python 3.11 a 3.13 (3.11 es el probado en Windows)
PY=""
for c in python3.11 python3.12 python3.13 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)'; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  if command -v brew >/dev/null 2>&1; then
    echo "Instalando Python 3.11 con Homebrew…"
    brew install python@3.11
    PY="$(brew --prefix python@3.11)/bin/python3.11"
  else
    echo "Falta Python 3.11. Instale Homebrew (https://brew.sh) y luego:  brew install python@3.11" >&2
    exit 1
  fi
fi
echo "Python: $PY"
"$PY" -m venv viaviva/.venv
viaviva/.venv/bin/python -m pip install --upgrade pip
viaviva/.venv/bin/python -m pip install -r viaviva/requirements-pc.txt

# .env sin secretos: la captura no necesita claves
[ -f .env ] || cp .env.example .env

# Leaflet local: el mapa funciona sin internet en el carro
mkdir -p viaviva/web/vendor/leaflet
for f in leaflet.js leaflet.css; do
  curl -fsSL "https://unpkg.com/leaflet@1.9.4/dist/$f" -o "viaviva/web/vendor/leaflet/$f" \
    || echo "Aviso: no se descargó $f (el mapa usará la versión simple)."
done

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Opcional: falta ffmpeg (solo para convertir videos HEVC del iPhone):  brew install ffmpeg"
fi
chmod +x viaviva.sh
cat <<'FIN'

Listo. Prueba sin iPhone:   ./viaviva.sh doctor --simulado ejemplo
Práctica de captura:        ./viaviva.sh capture --replay ejemplo --por-http --abrir
Salida de campo:            ./viaviva.sh doctor   y luego   ./viaviva.sh capture --abrir
La primera vez macOS puede preguntar si Python acepta conexiones entrantes: «Permitir» (si no, el celular no abre /marcar).
FIN
