# firmware/nodo-camara

Esqueleto PlatformIO para la **ESP32-CAM AI-Thinker** (ESP32 + OV2640 + 4 MB PSRAM).

## Qué hace

Espera órdenes del nodo de sensores por UART2 (115200 baud) y responde:

| Orden | Respuesta |
|---|---|
| `PING` | `PONG` (o `ERR,0,camara` si la cámara no inició) |
| `FOTO,<id>,<hora>` | captura → difuminado → JPEG en PSRAM → `OK,<id>,<bytes>` o `ERR,<id>,<codigo>` |

Conexión propuesta: GPIO 15 (TX del S3) → **GPIO 13** (RX de la CAM); **GPIO 14** (TX de la CAM) → GPIO 16 (RX del S3);
GND común; 1 kΩ en serie en cada línea. Se usan pines de la microSD interna, que no se usa.

**Privacidad:** la imagen se difumina en el mismo búfer antes de comprimirla, así que la original no queda en ningún lado.
Mientras no exista la detección de placas y rostros se difumina **todo** el cuadro.

## Compilar y subir

```powershell
cd firmware\nodo-camara
pio run
```

La ESP32-CAM no tiene USB: se sube con un adaptador USB-serie (FTDI/CH340) a GPIO 1/3, con GPIO 0 a GND al encender.
Si el kit trae la base "ESP32-CAM-MB", basta con el cable USB.

## Estado (26-oct-2026)

**Compila** (`espressif32 @ 6.9.0`): RAM estática 34 076 B (10,4 %), flash 362 941 B (11,5 %).
**Nada se ha probado en hardware.**

### `[VALIDAR EN PLACA]`

1. Que la cámara inicie (OV2640) y que la PSRAM se detecte (~4 MB).
2. Pines del enlace UART (13/14) y que el arranque no se vea afectado.
3. Tiempo de captura + difuminado + JPEG (se imprime por el monitor); debe caber en los 3 s que espera el S3.
4. Consumo con la cámara activa (picos de corriente: alimentación de 5 V estable).

### `[PENDIENTE]`

- Difuminado **selectivo** de placas y rostros (detección simple en el borde).
- Color y mayor resolución (hoy: escala de grises 320 × 240).
- Enviar la miniatura difuminada al S3 o a la red (hoy solo queda en PSRAM).
