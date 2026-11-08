#!/usr/bin/env bash
# VÍA VIVA en Raspberry Pi 4 (futuro/pi): venvs del bot y del ETL + servicios systemd. NO probado en la placa todavía.
# Uso: bash futuro/pi/instalar.sh   (desde ~/via-viva, con el usuario normal; pide sudo solo para systemd)
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$RAIZ"
for v in bot etl; do
  python3 -m venv "$v/.venv"
  "$v/.venv/bin/python" -m pip install --upgrade pip
  # Las versiones exactas (entornos/*.txt) son de Windows; si alguna no tiene rueda para ARM, se usan los requirements.
  "$v/.venv/bin/python" -m pip install -r "entornos/$v.txt" || "$v/.venv/bin/python" -m pip install -r "$v/requirements.txt"
done
"bot/.venv/bin/python" -m pip install psutil
[ -f .env ] || cp .env.example .env
for u in via-viva-bot.service via-viva-scraping.service via-viva-scraping.timer; do
  sed "s#__RAIZ__#$RAIZ#g; s#__USUARIO__#$USER#g" "futuro/pi/$u" | sudo tee "/etc/systemd/system/$u" > /dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable via-viva-bot.service via-viva-scraping.timer
sudo systemctl start via-viva-scraping.timer
echo "Listo. Poner el token en $RAIZ/.env y luego: sudo systemctl start via-viva-bot"
echo "Ver: systemctl list-timers via-viva* · journalctl -u via-viva-bot -f"
