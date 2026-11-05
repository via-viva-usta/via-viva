# Simulación en Wokwi

Hay dos formas. Las dos usan los mismos pines que el nodo real y la misma placa: **ESP32 DevKit V1 de 30 pines**
(`wokwi-esp32-devkit-v1`; sus pines se llaman `D21`, `RX2`, `GND.1`, ...).

`diagram.json` (en esta carpeta y en `firmware/nodo-sensores/`, son iguales) tiene: ESP32 DevKit V1, MPU-6050, microSD,
**DHT22 en GPIO 25 con pull-up de 10 kΩ**, pulsador en GPIO 26 y LED con 330 Ω en GPIO 33.

## A. wokwi.com (navegador, sin instalar nada) — proyecto chico de esta carpeta

1. Entrar a https://wokwi.com → **New Project** → **ESP32** (Arduino).
2. Reemplazar `sketch.ino` por el de esta carpeta.
3. Pestaña `diagram.json` → reemplazar por el de esta carpeta.
4. **Play**. En el monitor serie debe salir `MPU-6050: PASA` y `microSD: PASA`.
5. Clic en el MPU-6050 → mover el giro **Z** por encima de 15 °/s durante más de 1 s → sale `giro_izquierda`
   (o `giro_derecha` si es negativo). El botón rojo guarda `etiqueta_boton`. Todo se escribe en `/wokwi.csv` de la microSD.
   (El DHT22 está en el diagrama, pero este sketch chico no lo lee.)

## B. Wokwi para VS Code — firmware COMPLETO del nodo

1. Instalar la extensión **Wokwi Simulator** en VS Code (pide una licencia gratuita la primera vez).
2. Compilar: `pio run -e esp32dev` (desde `firmware/nodo-sensores`).
3. Abrir `firmware/nodo-sensores/diagram.json` → **Wokwi: Start Simulator**. Usa `wokwi.toml`, que apunta al
   `.bin` y al `.elf` compilados.
4. Si el DHT22 simulado responde, sale `[AMBIENTE] temperatura/humedad: dht22` (clic en el DHT22 para cambiar °C y
   % HR; sin probar). El LED debe dar **4 destellos** (no hay ADXL345 en Wokwi: ver los códigos del LED en `../README.md`).

## Qué NO se simula

| Pieza | Por qué | Qué se ve |
|---|---|---|
| ADXL345 | Wokwi no tiene el ADXL345 | `[ADXL345] ... NO RESPONDE`; no hay muestras ni eventos de la vía; LED con 4 destellos; gráfica vacía |
| VL53L0X | No existe en Wokwi | `VL53L0X: NO RESPONDE` |
| BH1750 | No existe en Wokwi (la fotorresistencia de Wokwi es analógica, no sirve) | `BH1750: NO RESPONDE` |
| GPS NEO-6M | No hay pieza de GPS | Velocidad 0; cada 5 s `[GPS] sin datos ... UART2 reiniciada` (es lo esperado sin GPS) |
| Punto de acceso Wi-Fi | Wokwi simula Wi-Fi como estación (red `Wokwi-GUEST`), no como punto de acceso | El servidor web puede no quedar accesible |
| Tiempos reales (jitter, % de CPU, corriente) | La simulación no reproduce la temporización del chip | Los números de E1–E4 **solo** valen medidos en la placa real |

## Estado

`sketch.ino` y el firmware completo compilan para `esp32dev` y `diagram.json` es JSON válido con los nombres de pines de
`wokwi-esp32-devkit-v1` (tomados del `board.json` oficial de Wokwi), pero **no he corrido la simulación** (Wokwi necesita su
página o la extensión con licencia). En particular, no sé si el controlador propio del DHT22 (`include/ambiente.h`) lee
bien el DHT22 simulado: Wokwi advierte que algunas librerías de DHT fallan en su ESP32. Si una conexión no carga, revisar
los nombres de pines en el editor de Wokwi.
