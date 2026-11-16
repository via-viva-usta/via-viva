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

# MapLibre local (el mismo mapa del tablero en línea): funciona sin internet en el carro
mkdir -p viaviva/web/vendor/maplibre
for f in maplibre-gl.mjs maplibre-gl-worker.mjs maplibre-gl.css; do
  curl -fsSL "https://cdn.jsdelivr.net/npm/maplibre-gl@6.17.0/dist/$f" -o "viaviva/web/vendor/maplibre/$f" \
    || echo "Aviso: no se descargó $f (el mapa se bajará de internet o usará la versión simple)."
done

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Opcional: falta ffmpeg (solo para convertir videos HEVC del iPhone):  brew install ffmpeg"
fi
chmod +x viaviva.sh

# «VIA VIVA.app» en ~/Applications (Launchpad y Dock): abre la app en su propia ventana (Edge o Chrome en modo app;
# si no hay ninguno, en el navegador). Sin probar en Mac.
APP="$HOME/Applications/VIA VIVA.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cat > "$APP/Contents/MacOS/VIA VIVA" <<APPSH
#!/bin/bash
cd "$RAIZ" && exec "$RAIZ/viaviva/.venv/bin/python" -m viaviva app
APPSH
chmod +x "$APP/Contents/MacOS/VIA VIVA"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>VIA VIVA</string>
  <key>CFBundleExecutable</key><string>VIA VIVA</string>
  <key>CFBundleIdentifier</key><string>co.edu.usta.viaviva</string>
  <key>CFBundleIconFile</key><string>viaviva</string>
  <key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>
PLIST
if command -v iconutil >/dev/null 2>&1 && command -v sips >/dev/null 2>&1; then
  ICONOS="$(mktemp -d)/viaviva.iconset"; mkdir -p "$ICONOS"
  for t in 16 32 128 256 512; do
    sips -z $t $t viaviva/web/icono/viaviva-512.png --out "$ICONOS/icon_${t}x${t}.png" >/dev/null
  done
  iconutil -c icns "$ICONOS" -o "$APP/Contents/Resources/viaviva.icns" || true
fi
echo "App creada: $APP (también puede arrastrarla al Dock)."
cat <<'FIN'

Listo. Prueba sin iPhone:   ./viaviva.sh doctor --simulado ejemplo
Práctica de captura:        ./viaviva.sh capture --replay ejemplo --por-http --abrir
Salida de campo:            ./viaviva.sh doctor   y luego   ./viaviva.sh capture --abrir
La primera vez macOS puede preguntar si Python acepta conexiones entrantes: «Permitir» (si no, el celular no abre /marcar).
FIN
