#!/usr/bin/env bash
# VÍA VIVA en la Raspberry Pi 4 (Raspberry Pi OS Bookworm 64 bits). [VALIDAR EN PLACA]: escrito sin la Pi.
# Uso (con internet, una sola vez):   cd ~/via-viva && bash pi/instalar.sh
# Pide sudo para apt, interfaces, systemd y el punto de acceso. Las claves NO van aquí: van en ~/via-viva/.env
#
# Hace: (1) paquetes, (2) SPI + I2C a 400 kHz + UART sin consola, (3) venv pi/.venv y etl/.venv, (4) Leaflet local
# (mapa sin internet), (5) .env, (6) punto de acceso WiFi VIA-VIVA en 192.168.4.1, (7) permiso de apagado seguro,
# (8) servicios systemd: via-viva-pi (captura + tablero) y el scraping diario de las 06:30.
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
cd "$RAIZ"
USUARIO="${SUDO_USER:-$USER}"
CONFIG=/boot/firmware/config.txt; [ -f "$CONFIG" ] || CONFIG=/boot/config.txt
paso() { printf '\n== %s\n' "$1"; }

paso "1/8 Paquetes del sistema"
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev python3-lgpio python3-gpiozero python3-spidev python3-smbus2 \
  python3-serial python3-libgpiod i2c-tools network-manager avahi-daemon sqlite3 curl

paso "2/8 SPI, I2C (400 kHz) y UART del GPS"
sudo raspi-config nonint do_spi 0
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_serial_hw 0     # UART encendido…
sudo raspi-config nonint do_serial_cons 1   # …sin la consola de Linux encima (el GPS habla por ahí)
grep -q '^dtparam=i2c_arm_baudrate=' "$CONFIG" || echo 'dtparam=i2c_arm_baudrate=400000' | sudo tee -a "$CONFIG" >/dev/null
sudo usermod -aG gpio,i2c,spi,dialout "$USUARIO"

paso "3/8 Entornos de Python"
python3 -m venv --system-site-packages pi/.venv
pi/.venv/bin/python -m pip install --upgrade pip
pi/.venv/bin/python -m pip install -r pi/requirements.txt
python3 -m venv etl/.venv
etl/.venv/bin/python -m pip install --upgrade pip
etl/.venv/bin/python -m pip install -r etl/requirements.txt

paso "4/8 Leaflet local (el mapa funciona sin internet; sin internet no hay fondo, sí calles y huecos)"
mkdir -p pi/web/vendor/leaflet
for f in leaflet.js leaflet.css; do
  curl -fsSL "https://unpkg.com/leaflet@1.9.4/dist/$f" -o "pi/web/vendor/leaflet/$f"
done

paso "5/8 Archivo .env (claves solo aquí)"
[ -f .env ] || cp .env.example .env
chmod 600 .env
# shellcheck disable=SC1091
set -a; . ./.env; set +a

paso "6/8 Punto de acceso WiFi VIA-VIVA (celular y tablet se conectan aquí; http://192.168.4.1)"
CLAVE_AP="${PI_AP_CLAVE:-}"
if [ -z "$CLAVE_AP" ]; then
  read -r -s -p "Clave del WiFi VIA-VIVA (mín. 8 caracteres; no se muestra ni se guarda en Git): " CLAVE_AP; echo
fi
if ! nmcli -t -f NAME con show | grep -qx via-viva-ap; then
  sudo nmcli con add type wifi ifname wlan0 con-name via-viva-ap autoconnect yes ssid VIA-VIVA mode ap \
    802-11-wireless.band bg ipv4.method shared ipv4.addresses 192.168.4.1/24 \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$CLAVE_AP"
else
  sudo nmcli con modify via-viva-ap wifi-sec.psk "$CLAVE_AP"
fi
unset CLAVE_AP

paso "7/8 Apagado seguro sin contraseña (solo 'systemctl poweroff', para el pulsador y la web)"
REGLA="$USUARIO ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff"
echo "$REGLA" | sudo tee /etc/sudoers.d/via-viva >/dev/null
sudo chmod 440 /etc/sudoers.d/via-viva
sudo visudo -cf /etc/sudoers.d/via-viva

paso "8/8 Servicios systemd"
for u in via-viva-pi.service via-viva-scraping.service via-viva-scraping.timer; do
  sed "s#__RAIZ__#$RAIZ#g; s#__USUARIO__#$USUARIO#g" "pi/sistemas/$u" | sudo tee "/etc/systemd/system/$u" >/dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable via-viva-pi.service via-viva-scraping.timer
sudo systemctl restart via-viva-pi.service
sudo systemctl start via-viva-scraping.timer

cat <<FIN

Listo. Falta (una vez):
  1. Copiar la base del PC con las calles de OSM:  scp data/via_viva.db $USUARIO@via-viva.local:$RAIZ/data/
  2. Crear los usuarios (cada quien escribe su contraseña):
       pi/.venv/bin/python -m pi.usuarios crear andres --rol editor --nombre "Andrés Cárdenas"
       pi/.venv/bin/python -m pi.usuarios crear alcaldia --rol alcaldia --nombre "Secretaría de Infraestructura"
  3. Reiniciar para aplicar SPI/I2C/UART:  sudo reboot
Luego: WiFi VIA-VIVA → http://192.168.4.1 (captura) y http://192.168.4.1/tablero
Ver: systemctl status via-viva-pi · journalctl -u via-viva-pi -f · systemctl list-timers 'via-viva*'
FIN
