# firmware/nodo-camara

Esqueleto PlatformIO para la **ESP32-CAM AI-Thinker** (ESP32 + OV2640 + 4 MB PSRAM propia del módulo de cámara).

## Qué hace

Espera órdenes del nodo de sensores por UART2 (115200 baud) y responde:

| Orden | Respuesta |
|---|---|
| `PING` | `PONG` (o `ERR,0,camara` si la cámara no inició) |
| `FOTO,<id>,<hora>` | captura → difuminado → JPEG en PSRAM → `OK,<id>,<bytes>` o `ERR,<id>,<codigo>` |

**Privacidad:** la imagen se difumina en el mismo búfer antes de comprimirla, así que la original no queda en ningún lado.
Mientras no exista la detección de placas y rostros se difumina **todo** el cuadro.

## Conexión con el nodo de sensores (ESP32 WROOM-32)

| Nodo de sensores | ESP32-CAM |
|---|---|
| GPIO 25 (TX, UART1) | GPIO 13 (RX) |
| GPIO 35 (RX, UART1) | GPIO 14 (TX) |
| GND | GND |

Poner 1 kΩ en serie en cada línea de datos. Se usan pines de la microSD interna de la cámara, que no se usa.
La ESP32-CAM se alimenta con **5 V estables** y un condensador de 470–1000 µF entre 5 V y GND (al encender la cámara
o el Wi-Fi los picos de corriente la reinician).

## Programarla con el adaptador USB-TTL CP2102 (sin base MB)

| CP2102 | ESP32-CAM |
|---|---|
| 5V | 5V |
| GND | GND |
| TXD | U0R (GPIO 3) |
| RXD | U0T (GPIO 1) |

1. Puentear **GPIO 0 a GND** (modo de programación) y conectar el CP2102 al PC.
2. Presionar el botón RST de la cámara (o desconectar y conectar 5 V).
3. `pio run -t upload` (desde esta carpeta). Si no encuentra el puerto, instalar el driver CP210x de Silicon Labs.
4. Al terminar: **quitar el puente GPIO 0–GND** y presionar RST para que corra el programa.
5. `pio device monitor` para ver los mensajes (UART0 a 115200).

Si la subida falla con "Failed to connect": revisar que TX y RX estén cruzados, que GPIO 0 esté en GND al reiniciar
y que la alimentación sea de 5 V (con 3,3 V muchas no arrancan).

## Compilar

```powershell
cd firmware\nodo-camara
pio run
```

## Estado (2-nov-2026)

**Compila** (`espressif32 @ 6.9.0`, placa `esp32cam`). **Nada se ha probado en hardware.**

### `[VALIDAR EN PLACA]`

1. Que la cámara inicie (OV2640) y que la PSRAM del módulo se detecte (~4 MB).
2. Pines del enlace UART (13/14) y que el arranque no se vea afectado.
3. Tiempo de captura + difuminado + JPEG (se imprime por el monitor); debe caber en los 3 s que espera el nodo.
4. Consumo con la cámara activa (picos de corriente: alimentación de 5 V estable y condensador).

### `[PENDIENTE]`

- Difuminado **selectivo** de placas y rostros (detección simple en el borde).
- Color y mayor resolución (hoy: escala de grises 320 × 240).
- Enviar la miniatura difuminada al nodo o a la red (hoy solo queda en PSRAM).
