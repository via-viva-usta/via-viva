# Simulación en Wokwi

Hay dos formas. Las dos usan los mismos pines que el nodo real.

## A. wokwi.com (navegador, sin instalar nada) — proyecto chico de esta carpeta

1. Entrar a https://wokwi.com → **New Project** → **ESP32** (Arduino).
2. Reemplazar `sketch.ino` por el de esta carpeta.
3. Pestaña `diagram.json` → reemplazar por el de esta carpeta (ESP32 DevKit, MPU-6050, microSD, botón, LED).
4. **Play**. En el monitor serie debe salir `MPU-6050: PASA` y `microSD: PASA`.
5. Clic en el MPU-6050 → mover el giro **Z** por encima de 15 °/s durante más de 1 s → sale `giro_izquierda`
   (o `giro_derecha` si es negativo). El botón rojo guarda `etiqueta_boton`. Todo se escribe en `/wokwi.csv` de la microSD.

## B. Wokwi para VS Code — firmware COMPLETO del nodo

1. Instalar la extensión **Wokwi Simulator** en VS Code (pide una licencia gratuita la primera vez).
2. Compilar: `pio run -e esp32dev` (desde `firmware/nodo-sensores`).
3. Abrir `firmware/nodo-sensores/diagram.json` → **Wokwi: Start Simulator**. Usa `wokwi.toml`, que apunta al
   `.bin` y al `.elf` compilados.

## Qué NO se simula

| Pieza | Por qué | Qué se ve |
|---|---|---|
| ADXL345 | Wokwi no tiene el ADXL345 | `[ADXL345] ... NO RESPONDE`; no hay muestras ni eventos de la vía |
| VL53L0X | No existe en Wokwi | `VL53L0X: NO RESPONDE` |
| GPS NEO-6M | No hay pieza de GPS | Velocidad 0 → el detector no dispara (activar "modo mesa" no sirve sin ADXL345) |
| ESP32-CAM | No existe en Wokwi | `[CAM] PING → (sin respuesta)` |
| Punto de acceso Wi-Fi | Wokwi simula Wi-Fi como estación (red `Wokwi-GUEST`), no como punto de acceso | El servidor web puede no quedar accesible |
| Tiempos reales (jitter, % de CPU, corriente) | La simulación no reproduce la temporización del chip | Los números de E1–E4 **solo** valen medidos en la placa real |

## Estado

`sketch.ino` compila para `esp32dev` y el `diagram.json` es JSON válido, pero **no he corrido la simulación** (Wokwi necesita
su página o la extensión con licencia). Si una conexión no carga, revisar los nombres de pines en el editor de Wokwi.
