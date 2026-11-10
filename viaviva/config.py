"""Configuración del nodo central Raspberry Pi 4 (decisión del 7-nov). Un solo lugar para pines, tasas y rutas.

Pines en numeración **BCM**, iguales a la tabla oficial del `02_HARDWARE/VIA_VIVA_Manual_Armado_v3_Pi4.pdf`
(apartado 5). ADXL345 #2 en CE1 (GPIO7, opcional). Pulsador: `dtoverlay=gpio-shutdown,gpio_pin=27` (apaga el
sistema). Se pueden cambiar sin tocar código con variables de entorno en `.env` (p. ej. `PI_PIN_INT1=17`).

| Señal                     | Pin BCM (físico)        | Bus / nota                                                   |
|---------------------------|-------------------------|--------------------------------------------------------------|
| ADXL345 SCLK/MISO/MOSI/CS | 11/9/10/8 (23/21/19/24) | SPI0, CE0, modo 3, 1,5 MHz (≤ 1,6 MHz: sin pausa en la FIFO) |
| ADXL345 INT1 (watermark)  | 17 (11)                 | Interrupción por flanco de subida (sustituye al DMA)         |
| I2C SDA / SCL             | 2 / 3 (3 / 5)           | I2C1 a 400 kHz: MPU-6050 0x68, VL53L0X 0x29, BH1750 0x23     |
| GPS NEO-6M TX → RX Pi     | 15 (10)                 | UART `/dev/serial0`, 9600 baud (RX del GPS a 14 es opcional) |
| DHT22 DATA                | 4 (7)                   | Pull-up 10 kΩ a 3V3; lectura tolerante a fallos              |
| Pulsador (a GND)          | 27 (13)                 | Apagado limpio del sistema (gpio-shutdown, pulsar 1 s)       |
| LED (con 330 Ω)           | 22 (15)                 | Lento = grabando; fijo = listo; rápido = falla de sensor     |
Todo a 3,3 V (los módulos con regulador a 5 V se alimentan del pin 2/4 pero sus señales deben quedar a 3,3 V).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env")
except ImportError:
    pass


def _ent(nombre: str, defecto: int) -> int:
    v = os.getenv(nombre, "").strip()
    return int(v) if v else defecto


# --- pines (BCM)
PIN_INT1 = _ent("PI_PIN_INT1", 17)
PIN_DHT22 = _ent("PI_PIN_DHT22", 4)
PIN_PULSADOR = _ent("PI_PIN_PULSADOR", 27)
PIN_LED = _ent("PI_PIN_LED", 22)
SPI_BUS, SPI_CS = 0, 0
SPI_HZ = 1_500_000
I2C_BUS = 1
UART_GPS = os.getenv("PI_UART_GPS", "/dev/serial0")
GPS_BAUD = 9600

# --- tasas
FS_ADXL_HZ = 200.0              # igual que el nodo ESP32 (hipótesis a validar con el espectro)
WATERMARK_FIFO = 16             # interrupción cada 16 muestras = 80 ms (la FIFO tiene 32; queda margen)
FS_MPU_HZ = 100.0
PERIODO_LUZ_S = 1.0
PERIODO_DISTANCIA_S = 0.05      # VL53L0X continuo ~20 Hz
PERIODO_AMBIENTE_S = 10.0       # DHT22: ≥ 2 s entre lecturas por hoja de datos; 10 s como el nodo
SOSTENER_APAGADO_S = 1.0       # gpio-shutdown: pulsar ~1 s (manual v3, paso 5f)

# --- servidor y datos
ID_NODO = os.getenv("PI_ID_NODO", "pi-01")
PUERTO = _ent("VIAVIVA_PUERTO", 8000)
PHYPHOX_URL = os.getenv("VIAVIVA_PHYPHOX_URL", "http://172.20.10.1:8080")   # iPhone de punto de acceso
FS_PHYPHOX_HZ = 100.0
SPI_CS_ADXL2 = 1                 # ADXL345 #2 en CE1 (opcional, manual v3)
_CAMPO = RAIZ.parent.parent / "06_CAMPO"   # 02_VIA_VIVA/06_CAMPO: datos crudos fuera del repo
DIR_GRABACIONES = Path(os.getenv("VIAVIVA_DIR_SESIONES") or os.getenv("PI_DIR_GRABACIONES") or
                       (_CAMPO / "sesiones" if _CAMPO.exists() else RAIZ / "data" / "raw" / "sesiones"))
LOG_R7 = RAIZ / "data" / "logs" / "r7.jsonl"
RETARDO_REACCION_S = float(os.getenv("VIAVIVA_RETARDO_S", "-1.0"))   # la marca se corre 1 s atrás (reacción humana)
# Teclas del etiquetado (mismas en el PC, el celular y la consola). U = deshacer la última.
ETIQUETAS = [("1", "hueco", "Hueco"), ("2", "resalto", "Resalto"), ("3", "grieta", "Grieta"), ("4", "parche", "Parche"),
             ("5", "tapa", "Tapa"), ("6", "obstaculo", "Obstáculo"), ("7", "via_buena", "Vía buena")]
VEL_MAX_KMH = 30.0               # protocolo de campo
QUIETO_INICIO_FIN_S = 60.0       # 1 min quieto al inicio y al final
MAX_M_TRAMO = 25.0              # ajuste a la calle (igual que etl.recorridos)
VENTANA_ETIQUETA_S = 3.0        # una etiqueta a ± 3 s de un disparo se le asigna a ese evento


@dataclass
class ParametrosUmbral:
    """Copia de `analysis.detector_umbral.ParametrosUmbral` (allá importa pandas, que la Pi no necesita).
    tests/test_pi_nucleo.py verifica que sean iguales."""
    v_min_kmh: float = 5.0
    k_rel: float = 6.0
    p2p_min_g: float = 0.30
    tau_base_s: float = 2.0
    ventana_p2p_s: float = 0.05
    refractario_s: float = 1.0
