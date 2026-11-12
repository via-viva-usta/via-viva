#!/usr/bin/env bash
# VÍA VIVA en la Raspberry Pi 4 (Raspberry Pi OS Lite 64 bits, manual de armado v3). [SIN PROBAR EN HARDWARE]
# Uso (con internet, una sola vez):   cd ~/via-viva && bash viaviva/instalar.sh [--punto-de-acceso]
# Pide sudo para apt, interfaces y systemd. Las claves NO van aquí: van en ~/via-viva/.env
#
# Hace: (1) paquetes, (2) SPI + I2C a 400 kHz + UART del GPS + gpio-shutdown en GPIO27 + sin Bluetooth (manual v3,
# paso 2), (3) venv viaviva/.venv, (4) MapLibre local, (5) .env, (6) [opcional] punto de acceso propio VIA-VIVA,
# (7) permiso de apagado desde la web, (8) servicios systemd: via-viva-pi (captura + tablero) y scraping diario.
# Red normal (manual v3): la Pi se conecta al HOTSPOT del celular, que da internet para sincronizar con Supabase.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"
USUARIO="${SUDO_USER:-$USER}"
AP=0; [ "${1:-}" = "--punto-de-acceso" ] && AP=1
CONFIG=/boot/firmware/config.txt; [ -f "$CONFIG" ] || CONFIG=/boot/config.txt
paso() { printf '\n== %s\n' "$1"; }
linea() { grep -qxF "$1" "$CONFIG" || echo "$1" | sudo tee -a "$CONFIG" >/dev/null; }

paso "1/8 Paquetes del sistema"
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev python3-numpy python3-lgpio python3-gpiozero python3-spidev \
  python3-smbus2 python3-serial python3-libgpiod i2c-tools network-manager avahi-daemon sqlite3 curl

paso "2/8 Interfaces (manual v3, paso 2)"
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_serial_hw 0     # UART encendido…
sudo raspi-config nonint do_serial_cons 1   # …sin la consola de Linux encima (el GPS habla por ahí)
linea 'dtparam=i2c_arm_baudrate=400000'
linea 'enable_uart=1'
linea 'dtoverlay=disable-bt'                # /dev/serial0 = UART completo para el GPS
linea 'dtoverlay=gpio-shutdown,gpio_pin=27' # pulsador: apagado limpio (systemd avisa a la captura con SIGTERM)
sudo usermod -aG gpio,i2c,spi,dialout "$USUARIO"
# gpsd (lo instala el manual para probar con gpsmon) toma /dev/serial0: la captura lee el GPS directo
if systemctl list-unit-files | grep -q '^gpsd'; then sudo systemctl disable --now gpsd.socket gpsd.service || true; fi

paso "3/8 Entorno de Python"
python3 -m venv --system-site-packages viaviva/.venv
viaviva/.venv/bin/python -m pip install --upgrade pip
viaviva/.venv/bin/python -m pip install -r viaviva/requirements.txt
python3 -m venv etl/.venv
etl/.venv/bin/python -m pip install -r etl/requirements.txt

paso "4/8 MapLibre local (el mapa del tablero local funciona sin internet)"
mkdir -p viaviva/web/vendor/maplibre
for f in maplibre-gl.mjs maplibre-gl-worker.mjs maplibre-gl.css; do
  curl -fsSL "https://cdn.jsdelivr.net/npm/maplibre-gl@6.17.0/dist/$f" -o "viaviva/web/vendor/maplibre/$f"
done

paso "5/8 Archivo .env (claves solo aquí)"
[ -f .env ] || cp .env.example .env
chmod 600 .env

if [ "$AP" = 1 ]; then
  paso "6/8 Punto de acceso propio VIA-VIVA (solo si no hay celular de hotspot; sin internet no hay sincronización)"
  set -a; . ./.env; set +a
  CLAVE_AP="${PI_AP_CLAVE:-}"
  [ -n "$CLAVE_AP" ] || { read -r -s -p "Clave del WiFi VIA-VIVA (mín. 8 caracteres; no se muestra): " CLAVE_AP; echo; }
  nmcli -t -f NAME con show | grep -qx via-viva-ap || sudo nmcli con add type wifi ifname wlan0 con-name via-viva-ap \
    autoconnect yes ssid VIA-VIVA mode ap 802-11-wireless.band bg ipv4.method shared ipv4.addresses 192.168.4.1/24 \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$CLAVE_AP"
  unset CLAVE_AP
else
  paso "6/8 Red: la Pi usa el hotspot del celular (configurado en Raspberry Pi Imager). Sin punto de acceso propio."
fi

paso "7/8 Apagado desde la página web (solo 'systemctl poweroff')"
echo "$USUARIO ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff" | sudo tee /etc/sudoers.d/via-viva >/dev/null
sudo chmod 440 /etc/sudoers.d/via-viva
sudo visudo -cf /etc/sudoers.d/via-viva

paso "8/8 Servicios systemd"
for u in via-viva-pi.service via-viva-scraping.service via-viva-scraping.timer; do
  sed "s#__RAIZ__#$RAIZ#g; s#__USUARIO__#$USUARIO#g" "viaviva/sistemas/$u" | sudo tee "/etc/systemd/system/$u" >/dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable via-viva-pi.service via-viva-scraping.timer
sudo systemctl start via-viva-scraping.timer

cat <<FIN

Listo. Falta (una vez):
  1. Copiar la base del PC con las calles de OSM:  scp data/via_viva.db $USUARIO@viavivapi.local:$RAIZ/data/
  2. Usuarios (cada quien escribe su contraseña):  viaviva/.venv/bin/python -m viaviva usuarios crear <u> --rol editor
  3. sudo reboot   (aplica SPI, I2C, UART y el pulsador). Después:  viaviva/.venv/bin/python -m viaviva doctor --source pi
Desde el celular (mismo hotspot): http://viavivapi.local/captura · /marcar · /tablero  (o la IP que muestre el doctor)
Ver: systemctl status via-viva-pi · journalctl -u via-viva-pi -f
FIN
