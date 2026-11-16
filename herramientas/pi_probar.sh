#!/usr/bin/env bash
# Pruebas del checklist de armado de la Raspberry Pi en UNA orden, con resumen OK / FALLA y qué revisar.
#   bash herramientas/pi_probar.sh            (desde la raíz del repo, en la Pi; pide sudo para parar el servicio)
#   bash herramientas/pi_probar.sh --sin-led  (no hace parpadear el LED)
# Si el servicio via-viva-pi está corriendo, lo para mientras prueba (ocupa SPI, UART y el LED) y lo vuelve a
# arrancar al final, aunque algo falle. Pines (BCM) iguales a viaviva/config.py: LED 22, ADXL345 en SPI0 CE0,
# GPS en /dev/serial0 a 9600 baud. NO PROBADO EN HARDWARE REAL todavía (16-nov-2026).
set -uo pipefail
cd "$(dirname "$0")/.."

SERVICIO=via-viva-pi
PIN_LED="${PI_PIN_LED:-22}"
UART="${PI_UART_GPS:-/dev/serial0}"
PY=viaviva/.venv/bin/python
[ -x "$PY" ] || PY=python3
CON_LED=1
[ "${1:-}" = "--sin-led" ] && CON_LED=0

OK=0; FALLAS=0; AVISOS=0
ok()    { printf '  [ OK  ] %s\n' "$1"; OK=$((OK + 1)); }
falla() { printf '  [FALLA] %s\n          Revise: %s\n' "$1" "$2"; FALLAS=$((FALLAS + 1)); }
aviso() { printf '  [AVISO] %s\n' "$1"; AVISOS=$((AVISOS + 1)); }

estaba_activo=0
if systemctl is-active --quiet "$SERVICIO" 2>/dev/null; then
  estaba_activo=1
  echo "El servicio $SERVICIO está activo: se para durante la prueba y se vuelve a arrancar al final."
  sudo systemctl stop "$SERVICIO"
fi
volver() {
  if [ "$estaba_activo" = 1 ]; then sudo systemctl start "$SERVICIO" || true; fi
}
trap volver EXIT

echo "== 1. Placa y alimentación"
if [ -r /proc/device-tree/model ]; then ok "Modelo: $(tr -d '\0' < /proc/device-tree/model)"; else aviso "No se pudo leer el modelo (¿no es una Raspberry Pi?)"; fi
ok "Sistema: $(. /etc/os-release 2>/dev/null; echo "${PRETTY_NAME:-desconocido}") · kernel $(uname -r)"
if command -v vcgencmd >/dev/null; then
  t=$(vcgencmd get_throttled | cut -d= -f2)
  if [ "$t" = "0x0" ]; then ok "get_throttled = 0x0 (sin bajo voltaje ni recorte por temperatura)"
  else falla "get_throttled = $t (bit 0 = bajo voltaje ahora; bit 16 = hubo bajo voltaje)" "fuente de 5 V / 3 A y cable USB-C cortos; ventilación"; fi
  ok "Temperatura: $(vcgencmd measure_temp | cut -d= -f2)"
else
  aviso "vcgencmd no está: no se pudo revisar el voltaje"
fi

echo "== 2. Interfaces"
if [ -e /dev/spidev0.0 ]; then ok "/dev/spidev0.0 existe (SPI0 CE0)"; else falla "/dev/spidev0.0 no existe" "sudo raspi-config nonint do_spi 0 y reiniciar (lo hace viaviva/instalar.sh)"; fi
if [ -e "$UART" ]; then ok "$UART existe -> $(readlink -f "$UART")"; else falla "$UART no existe" "enable_uart=1 en /boot/firmware/config.txt y consola serial desactivada (raspi-config); reiniciar"; fi

echo "== 3. ADXL345 por SPI (DEVID debe ser 0xE5)"
if [ -e /dev/spidev0.0 ]; then
  devid=$("$PY" - <<'FIN' 2>&1
import spidev
s = spidev.SpiDev()
s.open(0, 0)
s.mode = 3
s.max_speed_hz = 1_000_000
r = s.xfer2([0x80 | 0x00, 0x00])   # lectura del registro 0x00 (DEVID)
s.close()
print(f"0x{r[1]:02X}")
FIN
)
  if [ "$devid" = "0xE5" ]; then ok "DEVID = 0xE5 (ADXL345 responde)"
  else falla "DEVID = ${devid:-sin respuesta} (esperado 0xE5)" "cables SCL=GPIO11, SDO=GPIO9, SDA=GPIO10, CS=GPIO8, VCC a 3,3 V, GND; módulo en modo SPI"; fi
else
  falla "No se probó el ADXL345 (no hay SPI)" "ver punto 2"
fi

echo "== 4. GPS: líneas NMEA durante 5 s"
if [ -e "$UART" ]; then
  stty -F "$UART" 9600 raw -echo 2>/dev/null || true
  lineas=$(timeout 5 cat "$UART" 2>/dev/null | tr -d '\r' | grep -a -E '^\$G[NP][A-Z]{3},' || true)
  n=$(printf '%s\n' "$lineas" | grep -c '^\$' || true)
  if [ "$n" -gt 0 ]; then
    ok "$n líneas NMEA en 5 s (ej.: $(printf '%s\n' "$lineas" | head -1 | cut -c1-40))"
    if printf '%s\n' "$lineas" | grep -E '^\$G[NP]GGA,' | awk -F, '$7>0{f=1} END{exit !f}'; then ok "El GPS tiene posición (GGA con fix)"
    else aviso "El GPS habla pero sin posición todavía (normal en interiores o los primeros minutos)"; fi
  else
    falla "Sin líneas NMEA en $UART" "TX del GPS -> GPIO15 (RX de la Pi), 9600 baud, gpsd parado (sudo systemctl disable --now gpsd.socket)"
  fi
else
  falla "No se probó el GPS (no hay $UART)" "ver punto 2"
fi

echo "== 5. LED en GPIO$PIN_LED"
if [ "$CON_LED" = 0 ]; then
  aviso "Omitido (--sin-led)"
elif "$PY" - "$PIN_LED" <<'FIN' >/dev/null 2>&1
import sys, time
from gpiozero import LED
led = LED(int(sys.argv[1]))
for _ in range(3):
    led.on(); time.sleep(0.3); led.off(); time.sleep(0.3)
FIN
then
  ok "Se enviaron 3 parpadeos al LED: confírmelo a ojo"
else
  falla "No se pudo manejar el GPIO$PIN_LED" "python3-gpiozero y python3-lgpio instalados; LED con resistencia de 330 Ω a GND"
fi

echo "== 6. Servicio $SERVICIO"
if systemctl list-unit-files 2>/dev/null | grep -q "^$SERVICIO.service"; then
  if systemctl is-enabled --quiet "$SERVICIO"; then ok "$SERVICIO habilitado (arranca solo)"; else falla "$SERVICIO no está habilitado" "sudo systemctl enable $SERVICIO"; fi
  [ "$estaba_activo" = 1 ] && ok "$SERVICIO estaba activo (se vuelve a arrancar al terminar)" \
                           || aviso "$SERVICIO no estaba activo. Últimas líneas: journalctl -u $SERVICIO -n 30"
else
  falla "$SERVICIO no está instalado" "bash viaviva/instalar.sh"
fi

echo
echo "Resumen: $OK OK · $FALLAS FALLA · $AVISOS AVISO"
[ "$FALLAS" = 0 ]
