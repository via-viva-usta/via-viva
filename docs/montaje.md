# Montaje del nodo VÍA VIVA (ESP32 WROOM-32)

Guía para armar y probar el hardware **por partes**. Responsable: Dany (área A), apoyo Juan Diego.
Programas de prueba: `firmware/nodo-sensores/pruebas/` (cada uno termina con `RESULTADO: PASA` o `FALLA` y una pista).

## 1. Tabla de conexiones

| Componente | Pin del módulo | GPIO ESP32 | Alimentación | Notas |
|---|---|---|---|---|
| **ADXL345** (GY-291) | CS | 4 | 3V3 + GND | SPI por VSPI. Atornillado plano a la base (es el sensor principal) |
| | SCL/SCK | 18 | | |
| | SDO/MISO | 19 | | |
| | SDA/MOSI | 23 | | |
| | INT1 | 34 | | Solo entrada; el INT1 empuja la línea, no necesita resistencia |
| **MPU-6050** (GY-521) | SDA / SCL | 21 / 22 | 3V3 + GND | I2C 0x68 (AD0 a GND o suelto). **X hacia adelante del carro, Z hacia arriba** |
| **VL53L0X** | SDA / SCL | 21 / 22 | 3V3 + GND | I2C 0x29, mismo bus. XSHUT suelto. Apunta al piso |
| **GPS NEO-6M** | TX → | 16 (RX2) | 5 V o 3V3 (según el módulo) + GND | 9600 baud. Antena hacia el cielo |
| | RX ← | 17 (TX2) | | |
| **microSD** | CS / SCK / MOSI / MISO | 32 / 14 / 13 / 27 | 5 V si el módulo tiene regulador (AMS1117), si no 3V3 | HSPI por la matriz GPIO. Tarjeta en **FAT32** |
| **Pulsador** | una pata / otra | 26 / GND | — | Pull-up interno; antirrebote por software |
| **LED** | ánodo (con 220–330 Ω) / cátodo | 33 / GND | — | |
| **BME280** (GY-BME280) | SDA / SCL | 21 / 22 | **3V3** + GND | I2C 0x76 (SDO a GND; 0x77 si SDO a 3V3). Si la prueba dice ID 0x58 es un **BMP280** (sin humedad): usar DHT22 |
| **DHT22** (solo si no hay BME280) | DATA | 25 | 3V3 + GND | Pull-up de 10 kΩ a 3V3 (el módulo de 3 pines la trae). Cable < 1 m |
| **BH1750** (GY-302, opcional) | SDA / SCL / ADDR | 21 / 22 / GND | 3V3 + GND | I2C 0x23 (ADDR a GND). Sensor mirando hacia arriba, sin sombra de la caja |

> **3-nov-2026:** la ESP32-CAM y el CP2102 salieron del diseño (la evidencia la toma el celular, `docs/protocolo_fotos.md`).
> Los GPIO 25 y 35 quedaron libres; el 25 se usa para el DHT22.

Pines que **no** se usan: 0, 2, 5, 12, 15 (arranque), 6–11 (flash), 1 y 3 (monitor serie). 34–39 solo entradas, sin pull-up.

## 2. Checklist antes de energizar

- [ ] Todos los GND unidos (ESP32, sensores, GPS, microSD, fuente).
- [ ] Ningún sensor de 3,3 V conectado a 5 V (ADXL345, MPU-6050, VL53L0X, BME280 y BH1750 van a **3V3**).
- [ ] Nada conectado a los pines 0, 2, 5, 12 ni 15.
- [ ] TX del GPS → GPIO 16 (cruzado: TX con RX).
- [ ] Cables de SPI cortos (< 20 cm) y lejos de los de alimentación.
- [ ] La microSD formateada en FAT32 y puesta antes de encender.
- [ ] Multímetro: 3,3 V entre 3V3 y GND.

## 3. Orden de prueba

Un componente a la vez; si uno falla, no seguir sumando. Desde `firmware/nodo-sensores/pruebas`:

| # | Prueba | Comando | Qué debe salir |
|---|---|---|---|
| 1 | Placa sola | `pio run -e boton_led -t upload` y `pio device monitor` | LED parpadea 3 veces; 3 pulsaciones detectadas |
| 2 | Bus I2C | `pio run -e i2c -t upload` | Dispositivos en 0x68 y 0x29 |
| 3 | MPU-6050 | `pio run -e mpu6050 -t upload` | WHO_AM_I, \|a\| ≈ 1 g; girar a la izquierda → giro Z **positivo** |
| 4 | VL53L0X | `pio run -e vl53l0x -t upload` | ≥ 45/50 lecturas válidas, desviación < 15 mm |
| 5 | ADXL345 | `pio run -e adxl345 -t upload` | DEVID 0xE5, \|a\| ≈ 1 g, INT1 activo |
| 6 | microSD | `pio run -e microsd -t upload` | Monta, escribe 256 KB > 50 KB/s y relee igual |
| 7 | GPS | `pio run -e gps -t upload` | Datos y NMEA bajo techo; fijación **al aire libre** |
| 8 | BME280 | `pio run -e bme280 -t upload` | Fórmula PASA; ID 0x60; 10 lecturas; Tunja ≈ 730–760 hPa; soplar sube la humedad |
| 8b | DHT22 (si no hay BME280) | `pio run -e dht22 -t upload` | ≥ 8 de 10 lecturas correctas |
| 8c | BH1750 | `pio run -e bh1750 -t upload` | Responde en 0x23; tapar el sensor baja la luz |
| 9 | Todo junto | `cd ..` y `pio run -t upload` | Arranque con todo `OK`, página http://192.168.4.1 con la tarjeta **Ambiente**, `overruns=0`, `ambiente_NNN.csv` con una fila cada 10 s |

Anotar cada resultado en el issue #1 de GitHub.

## 4. Errores típicos

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Se reinicia solo, "Brownout detector was triggered" | Alimentación débil (cable USB delgado, puerto del PC) | Cable corto y grueso; cargador de 5 V / 2 A; condensador de 100–470 µF en 5 V |
| No arranca con la microSD puesta | Algo conectado a GPIO 12 (fija el voltaje de la flash) | Revisar que la microSD esté en 14/27/13/32, nunca en 12 |
| "Failed to connect to ESP32" al subir | No entra en modo de programación | Mantener BOOT al empezar a subir; cerrar el monitor serie |
| GPS: datos llegan pero nunca hay fijación | **Bajo techo no hay señal** | Salir a cielo abierto; la primera fijación puede tardar 1–5 min |
| GPS: no llega nada | TX/RX sin cruzar o 3,3 V insuficiente | TX del GPS → 16; probar a 5 V si el módulo tiene regulador |
| microSD no monta | Tarjeta en **exFAT** (≥ 64 GB) o mal formateada | Formatear en **FAT32** (tarjeta de ≤ 32 GB); revisar 5 V del módulo |
| VL53L0X da 8190 o timeouts **al sol** | La luz infrarroja del sol satura el sensor | Sombra: tubo o visera alrededor del sensor; anotarlo como limitación |
| VL53L0X o MPU con errores en el carro | Cable I2C largo (> 1 m) a 400 kHz | Bajar I2C a 100 kHz, cable trenzado, o acercar el sensor a la caja |
| BME280 responde pero la humedad sale vacía | Es un **BMP280** (ID 0x58), muy común en módulos baratos | Usar DHT22 en GPIO 25 para la humedad |
| Temperatura del nodo 3–8 °C más alta que la real | El sensor está dentro de la caja, junto a la ESP32 o al sol | Sacarlo de la caja (cable de 20–30 cm), a la sombra y con aire |
| ADXL345 responde 0x00 o 0xFF | CS mal o módulo en modo I2C | CS a GPIO 4; algunos GY-291 traen SDO/ALT a GND (forzar SPI con CS) |
| `overruns > 0` en la línea E1 | El watermark 31 deja solo 5 ms de margen | Bajar `FIFO_WATERMARK` a 16–24 en `include/config.h` |

## 5. Dónde va cada cosa

### En la baquela (placa perforada, ~7 × 9 cm)

```
 ┌──────────────────────────────────────────────┐
 │ [microSD]                         [GPS → cable │
 │  borde, ranura hacia afuera        a la antena]│
 │                                                │
 │        ┌───────────────────────┐   [ADXL345]   │
 │        │   ESP32 DevKit 30     │   atornillado │
 │        │   (en espadines,      │   plano, cerca│
 │        │    USB hacia el borde)│   del centro  │
 │        └───────────────────────┘   [MPU-6050]  │
 │                                    X → adelante│
 │ [LED] [pulsador]   [bornera 5V/GND] [conector  │
 │  (cable a la tapa)                  I2C láser] │
 └──────────────────────────────────────────────┘
```

- ESP32 en **espadines hembra** (se puede cambiar si se daña), USB hacia un borde para programar sin desarmar.
- **ADXL345 y MPU-6050 rígidos** a la baquela (tornillo + separador), no colgando de cables: si se mueven, miden su
  propio movimiento. Marcar la flecha X del MPU-6050 hacia la parte delantera de la caja.
- microSD en el borde, con la ranura accesible desde fuera de la caja.
- Bornera de 5 V / GND para la entrada de alimentación.
- **BME280 / DHT22 fuera de la caja** (cable de 20–30 cm): dentro se calienta con la ESP32 y mide mal.

### En la caja y en el carro

- Caja fijada al **piso o a la consola** con velcro industrial (no a una superficie que vibre sola, como una bandeja).
  La flecha "ADELANTE" de la caja hacia el frente del carro.
- **GPS:** antena cerca del parabrisas, con vista al cielo.
- **BME280 / DHT22:** con el carro cerrado mide la temperatura **de la cabina**, no la de la calle. Para el clima del dataset
  de fotos, poner el sensor afuera a la sombra (p. ej. en el retrovisor dentro de un vaso plástico perforado) o llevar el
  nodo encendido en la mano/morral mientras se toman las fotos. Si va dentro, anotarlo: esos datos no sirven como clima.
- **BH1750:** mirando al cielo (tablero junto al parabrisas o fuera); solo indica luz del día/noche/nublado.
- **VL53L0X:** apuntando al piso. El diseño lo pone en el bómper, pero un cable I2C de 2 m es poco confiable: primero
  probar dentro del carro apuntando al piso por la puerta o un orificio; si va al bómper, I2C a 100 kHz y cable trenzado.
- **Alimentación:** cargador de carro de 5 V / 2 A (o power bank) para el ESP32; medir la corriente con el
  tester USB (ver `docs/experimentos.md`).
- El **pulsador** al alcance del copiloto (nunca del conductor); en los recorridos se puede usar la página web del nodo.
