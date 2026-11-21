# Conectar y validar la Raspberry Pi 4 — paso a paso

**Hardware esperado (falta confirmarlo en el equipo):** Raspberry Pi 4 Model B de 4 GB de RAM, Cortex-A72 de 64 bits y
microSD de 64 GB (almacenamiento, no RAM).

**Nada de esto se ha probado todavía en la Pi.** Cada paso dice qué cambia. Los pasos 1–4 son de solo lectura.

## 1. Encontrarla en la red, sin escanear rangos

Use la misma red para la Pi y el PC: el hotspot del iPhone A o el WiFi configurado en Raspberry Pi Imager.

1. **Por nombre.** En el PC (PowerShell):
   - `Resolve-DnsName viavivapi.local`
   - `Resolve-DnsName raspberrypi.local`

   El nombre `viavivapi` es el que espera `instalar.sh`; `raspberrypi` es el de Imager por defecto.
2. **Por la tabla ARP del PC.** Solo lee lo que el PC ya vio; no escanea:
   ```powershell
   Get-NetNeighbor -AddressFamily IPv4 | Where-Object LinkLayerAddress -match '^(B8-27-EB|DC-A6-32|E4-5F-01|D8-3A-DD|2C-CF-67|28-CD-C1)'
   ```
   Esos prefijos son los de Raspberry Pi.
3. **En el router o el celular de hotspot:** la lista de equipos conectados.
4. **Si nada funciona:** monitor y teclado en la Pi, y ejecutar `hostname -I`.

No comparta en el chat la IP pública ni el nombre de la red. La IP local (192.168.x.x o 172.20.10.x) basta.

## 2. Entrar por SSH

- Comando: `ssh <usuario>@viavivapi.local`, o `ssh <usuario>@<IP local>`.
- La contraseña se escribe **solo en la terminal**, nunca en el chat.
- Si SSH no responde, actívelo en Imager (pestaña Servicios) y vuelva a grabar la tarjeta, o use monitor y teclado.
- No cambie la red ni la IP hasta que SSH funcione.

## 3. Estado del equipo (solo lectura)

En la Pi:
```bash
hostname -I; uname -m; free -h; df -h /; cat /proc/device-tree/model; echo; vcgencmd get_throttled
```

Se espera:
- `aarch64`;
- `Mem total` ≈ 3,7 Gi;
- `/` ≈ 58 G;
- «Raspberry Pi 4 Model B»;
- `throttled=0x0`. Un valor distinto indica fuente débil: use la fuente oficial de 5,1 V y 3 A.

Si el repo ya está en la Pi, el informe completo, que no muestra el SSID ni claves, se obtiene así:
```bash
cd ~/via-viva && bash herramientas/pi_estado.sh > ~/pi_estado.txt; cat ~/pi_estado.txt
```

## 4. Sensores conectados (solo lectura)

`pi_estado.sh` muestra las interfaces activadas, `/dev/spidev0.*`, `/dev/serial0` y los dispositivos I2C:

| Sensor | Conexión | Valor esperado |
|---|---|---|
| MPU-6050 | I2C | 0x68 |
| VL53L0X | I2C | 0x29 |
| BH1750 | I2C | 0x23 |
| ADXL345 | SPI0 CE0 | INT1 en GPIO17 |
| ADXL345 #2 | SPI0 CE1 | — |
| GPS | `/dev/serial0` | 9600 baudios |
| DHT22 | GPIO4 | — |
| Pulsador | GPIO27 | — |
| LED | GPIO22 | — |

Las lecturas reales salen en el paso 5, con `pi_probar.sh` y `doctor`.

## 5. Instalar, diagnosticar y guardar el resultado (**cambia el sistema**: confirmar antes)

```bash
git clone https://github.com/via-viva-usta/via-viva.git ~/via-viva && cd ~/via-viva
bash viaviva/instalar.sh
```

**Qué cambia `instalar.sh`** (pide sudo en la terminal):
- instala paquetes con `apt`;
- activa SPI, I2C y UART, y quita la consola del UART;
- agrega `enable_uart=1`, `dtoverlay=disable-bt` y `gpio-shutdown` (GPIO27) a `config.txt`. Esto apaga el Bluetooth;
- agrega el usuario a los grupos gpio, i2c, spi y dialout;
- desactiva `gpsd`;
- crea `.env` (permisos 600);
- permite apagar desde la web;
- instala el servicio `via-viva-pi` y lo **activa al arranque**.

Lo que **no** cambia sin opciones: la red. El punto de acceso propio solo se crea con la opción `--ap`.

Después hay que reiniciar (`sudo reboot`) para que se apliquen SPI, I2C y UART. Luego:
```bash
cd ~/via-viva
bash herramientas/pi_probar.sh 2>&1 | tee ~/pi_probar.txt          # requiere el PR #41 en main
viaviva/.venv/bin/python -m viaviva doctor --source pi 2>&1 | tee ~/doctor.txt
systemctl status via-viva-pi --no-pager | head -12
```

## 6. Prueba corta de mesa, auditoría y respaldo

Siga `docs/SALIDA_PI.md`, sección A (A5–A9):
- 3 min de captura con 3 golpes de dedo;
- una marca por clase;
- 2 destellos.

Después:
```bash
viaviva/.venv/bin/python -m herramientas.auditar_sesion <carpeta_sesion> --json ~/auditoria_mesa.json
viaviva/.venv/bin/python -m herramientas.comparar_detectores <carpeta_sesion> --html ~/mesa.html
```

Para respaldar, en el PC: `scp -r <usuario>@viavivapi.local:<carpeta_sesion> C:\VIA_VIVA_DATOS\pi_mesa\`.

Planee la salida de campo solo con 0 FALLA en la auditoría de mesa.

## Qué solo se valida con la Pi y los sensores reales

- Frecuencia efectiva del ADXL345, que hoy es de 200 Hz por hipótesis, y pérdidas de la FIFO.
- Latencia del pin de interrupción.
- Rango y saturación de cada sensor.
- Desfase entre ADXL #1, ADXL #2 y MPU.
- Fijación y hora del GPS sin internet.
- Alimentación en el carro.
- Temperatura dentro de la caja.
- Apagado con el pulsador.
- Escritura en la microSD durante 30 min.
- Detectores con señales reales y el montaje real.
