# Presupuesto de VÍA VIVA (3-nov-2026)

Plan del 3-nov: ESP32 normal con los sensores ya comprados + sensores de ambiente; **la foto la toma el celular**.
Salen del diseño la ESP32-CAM y el CP2102 (código en `futuro/`). El detalle editable está en la hoja **"3-nov celular"**
de `02_COMPRAS\VIA_VIVA_Cotizacion.xlsx` (fuera del repo; las hojas anteriores quedan como historia y hay respaldo en
`VIA_VIVA_Cotizacion_antes_3nov.xlsx`).

Fuentes de precio: cotización de Ferretrónica (Tunja) del 21-oct; ESP32 WROOM-32 de la hoja "Opcionales"; DHT22 y BH1750
consultados en ferretronica.com el 3-nov. **Precios de cotización, no de factura**: actualizar con lo pagado.

| Ítem | Cant. | COP | Estado |
|---|---|---|---|
| Acelerómetro ADXL345 (1 de repuesto) | 2 | 24.000 | sigue |
| MPU-6050 | 1 | 11.000 | sigue |
| GPS NEO-6M V2 | 1 | 38.000 | sigue |
| Módulo microSD SPI | 1 | 5.000 | sigue |
| microSD SanDisk 16 GB | 1 | 37.000 | sigue |
| Caja plástica REF 9 | 1 | 13.000 | sigue |
| Baquela 9 × 15 | 1 | 4.800 | sigue |
| Pulsador | 1 | 1.300 | sigue |
| Dupont × 40 | 2 | 16.000 | sigue |
| Tester USB | 1 | 9.500 | sigue |
| LEDs, resistencias, headers | 1 | 6.500 | sigue |
| VL53L0X | 1 | 25.000 | sigue |
| ESP32 DevKit 30 pines (WROOM-32) | 1 | 35.000 | sigue (decisión 2-nov) |
| **DHT22** (temperatura y humedad) | 1 | **22.000** | **nuevo** (el BME280 no aparece en Ferretrónica el 3-nov) |
| **BH1750** (luz), opcional | 1 | **8.000** | **nuevo** |
| **Subtotal** | | **256.100** | |
| Imprevistos 5 % | | 12.800 | |
| **Total** | | **268.900** | 67.225 por persona (4) |
| **Nuevo por comprar** | | **30.000** | DHT22 + BH1750 |

**Retirado:** ESP32-CAM con placa de programación (48.000 en la cotización), CP2102, ESP32-S3 + envío (87.000).
**Trabajo futuro (sin costo hoy):** módulo láser de cuadrícula, OBD2 ELM327 Bluetooth de solo lectura.
**Alternativa:** BME280 en Sigma Electrónica (Bogotá) a 23.800 + envío, en lugar del DHT22 (el firmware acepta
cualquiera de los dos y detecta si un "BME280" es en realidad un BMP280 sin humedad).
**Sin costo:** el celular de cada integrante, la impresión de la tarjeta ArUco (`docs/tarjeta_aruco.pdf`) y un metro o
regla. Termohigrómetro de mano solo si alguien tiene uno.

Comparación: el 2-nov se había anotado "≈ 330.000 COP" (sin desglose en el repo); con la cotización del 21-oct y sin la
ESP32-CAM ni la S3 el total da 268.900.
