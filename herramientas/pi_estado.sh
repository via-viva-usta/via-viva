#!/usr/bin/env bash
# Estado de la Raspberry Pi en SOLO LECTURA: no instala, no cambia red ni servicios, no pide sudo, no reinicia.
#   bash herramientas/pi_estado.sh                 (desde la carpeta del repo en la Pi; o copiándolo solo)
#   bash herramientas/pi_estado.sh > pi_estado_$(date +%Y%m%d_%H%M).txt
# No imprime el nombre de la red WiFi (SSID) ni claves. Las IP que muestra son de la red local.
# Pines esperados (viaviva/config.py): ADXL345 SPI0 CE0 (+ INT1 GPIO17), ADXL345 #2 CE1, I2C bus 1
# (MPU-6050 0x68, VL53L0X 0x29, BH1750 0x23), GPS /dev/serial0 a 9600, DHT22 GPIO4, pulsador GPIO27, LED GPIO22.
set -u
t() { printf '\n== %s\n' "$1"; }
o() { "$@" 2>&1 || echo "(no disponible: $*)"; }

t "Fecha y equipo"
date -Is
o hostname
o cat /proc/device-tree/model; echo
o uname -m
o getconf LONG_BIT
awk -F: '/^Model|^Hardware|^Revision/{print}' /proc/cpuinfo 2>/dev/null
o lscpu | grep -E 'Model name|Architecture|CPU\(s\):'

t "Memoria (RAM) y almacenamiento (microSD)"
o free -h
o df -h /
o lsblk -d -o NAME,SIZE,TYPE,MODEL

t "Sistema operativo"
o grep -E '^(PRETTY_NAME|VERSION_CODENAME)=' /etc/os-release
o uname -r

t "Alimentación y temperatura (0x0 = sin problemas)"
o vcgencmd get_throttled
o vcgencmd measure_temp

t "Reloj (NTP); sin internet la app toma la hora del GPS"
o timedatectl show -p NTPSynchronized -p TimeUSec -p Timezone

t "Red (sin SSID)"
o hostname -I
o ip -br link
command -v nmcli >/dev/null && o nmcli -t -f DEVICE,TYPE,STATE device

t "Servicios"
for s in ssh via-viva-pi via-viva-scraping.timer; do printf '%-26s %s / %s\n' "$s" \
  "$(systemctl is-enabled "$s" 2>/dev/null || echo -)" "$(systemctl is-active "$s" 2>/dev/null || echo -)"; done

t "Interfaces de los sensores (raspi-config: 0 = activada)"
for q in get_spi get_i2c get_serial_hw get_serial_cons; do
  printf '%-16s %s\n' "$q" "$(raspi-config nonint "$q" 2>/dev/null || echo '?')"; done
o ls -l /dev/spidev0.0 /dev/spidev0.1 /dev/i2c-1 /dev/serial0
grep -E '^(enable_uart|dtoverlay=disable-bt|dtoverlay=gpio-shutdown)' /boot/firmware/config.txt /boot/config.txt 2>/dev/null

t "Dispositivos I2C en el bus 1 (esperados: 68 MPU-6050, 29 VL53L0X, 23 BH1750)"
if command -v i2cdetect >/dev/null; then o i2cdetect -y 1; else echo "(i2c-tools no instalado)"; fi

t "Python y proyecto"
o python3 --version
if [ -d .git ]; then o git log -1 --format='%h %ad %s' --date=short; o git status --short --branch | head -5; fi
[ -x viaviva/.venv/bin/python ] && o viaviva/.venv/bin/python -c "import numpy, fastapi; print('numpy', numpy.__version__, '· fastapi', fastapi.__version__)"
[ -f .env ] && echo ".env presente (no se muestra)" || echo ".env ausente"
echo
echo "Fin. Antes de compartir esta salida, revise que no tenga datos privados."
