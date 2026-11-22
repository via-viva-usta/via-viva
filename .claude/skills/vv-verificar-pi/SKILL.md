---
name: vv-verificar-pi
description: Diagnóstico de la Raspberry Pi 4 de VÍA VIVA (modelo, sistema, espacio, hora, dependencias, servicio, sensores con pi_probar.sh y viaviva doctor). Se detiene y da pasos concretos si la Pi no está disponible; nunca finge pruebas en el dispositivo.
disable-model-invocation: true
---

# Verificar la Raspberry Pi

1. **¿Estamos en la Pi?** `cat /proc/device-tree/model` (debe decir «Raspberry Pi 4»).
   - Si no: buscar en la red, sin iniciar sesión (`Resolve-DnsName raspberrypi.local`, `Get-NetNeighbor` con OUI de
     Raspberry).
   - Luego **detenerse** y dar los pasos: encenderla, conectarla al mismo WiFi o hotspot y abrir una terminal en ella.
   - No pedir contraseñas.
2. **En la Pi**, desde la carpeta del repo, en este orden y mostrando la salida de cada uno:
   - `uname -a`, `cat /etc/os-release | head -3`;
   - `df -h /`, `free -h`, `vcgencmd measure_temp` y `vcgencmd get_throttled`. Un valor distinto de `0x0` en
     `get_throttled` = fuente débil;
   - `timedatectl`;
   - `systemctl is-active via-viva-pi`;
   - `ls /dev/spidev0.* /dev/serial0` e `i2cdetect -y 1` (direcciones esperadas: 0x68 MPU-6050, 0x29 VL53L0X,
     0x23 BH1750);
   - `bash herramientas/pi_probar.sh` (la sección 6 da FALLA mientras el servicio esté deshabilitado a propósito);
   - `viaviva/.venv/bin/python -m viaviva doctor --source pi`.
3. **Antes de cualquier cambio en la Pi:** respaldar la carpeta de sesiones. Copiar, nunca mover. **No copiar `.env`**
   (tiene claves): si hace falta, anotar qué variables define, sin sus valores.
4. **Informe:** tabla de lo verificado frente a lo que falta, con la salida real. Lo que no se ejecutó queda como «NO PROBADO».

Reglas:
- No editar `viaviva/sensores.py`, el servicio ni el firmware sin tarea explícita.
- No reiniciar ni apagar la Pi sin pedirlo.
