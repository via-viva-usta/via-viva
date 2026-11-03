# Experimentos de arquitectura E1–E4 (cómo medirlos)

Responsable: Dany (área A), apoyo Andrés. Los números del informe salen **solo** de estas mediciones en la placa real.

## Qué mide el firmware y dónde queda

Todo queda en la microSD, en `exp_NNN.csv` (una sesión por arranque), con filas `t_ms,experimento,condicion,variable,valor`.
También sale por el monitor serie en líneas `EXP,...`.

| Exp. | Pregunta | Cuándo se mide | Variables |
|---|---|---|---|
| **E1** | ¿Polling, interrupción por muestra o FIFO + DMA ping-pong? | Cada 5 s en operación | muestras vs. esperadas (% perdidas), overruns de la FIFO, bloques perdidos, jitter, intervalo mín/máx, % de CPU de cada núcleo, % de tiempo leyendo |
| **E2** | ¿Pesos del modelo en flash o en SRAM? | Al arrancar (sin tareas) | Latencia de la red 1D float32 con pesos en flash vs. copiados a SRAM: primera llamada (caché fría), media, mín, máx |
| **E3** | ¿float32 o int8? | Al arrancar | Latencia float32 vs. int8 (SRAM y flash), bosque emlearn, tamaño de los pesos, misma clase en ambos |
| **E4** | ¿I2C o SPI? | Al arrancar + cada 5 s | 500 lecturas del MPU-6050 (I2C 400 kHz, 14 B) vs. del ADXL345 (SPI 1,5 MHz, 7 B): µs por lectura, µs por byte, % de CPU a la tasa de uso |
| MEM | RAM y flash | Al arrancar | heap libre y total, tamaño del programa, flash libre |

**Ojo:** E2/E3 usan hoy un modelo entrenado con datos **sintéticos** (`MODELO_SINTETICO 1`). Sirve para la latencia
(no depende de los valores de los pesos), pero el F1 de E3 hay que sacarlo de `analysis/entrenar_detector.py` con
datos reales. La red es pequeña (~3 KB en float32): cabe entera en la caché de flash, así que E2 puede mostrar poca
diferencia después de la primera llamada; por eso se reporta también la primera (fría).

## Procedimiento

### E1 (tres corridas, una por modo)

Mismas condiciones en las tres: microSD, GPS y sensores de ambiente conectados, **celular conectado a la página web** (Wi-Fi activo).

```powershell
cd firmware\nodo-sensores
pio run -e esp32dev -t upload          # FIFO + DMA (modo normal)
pio run -e e1_polling -t upload        # polling cada 5 ms
pio run -e e1_int_muestra -t upload    # una interrupción por muestra
```

Para cada modo: encender, esperar 30 s, dejar correr **al menos 3 minutos** (36 filas de 5 s), apagar. Mejor en el carro
andando (vibración real); si no, sobre la mesa. El modo activo se ve en la página web ("modo E1").

### E2, E3, E4 y memoria

Se miden solos en cada arranque (antes de crear las tareas). Basta con encender el nodo 3 veces y quedarse con el
promedio. E4 también queda en operación (`condicion = operacion`).

### Copiar los datos

Sacar la microSD y copiar sus archivos a `data/raw/nodo/<fecha>_<modo>/` (por ejemplo `2026-11-05_fifo_dma/`).
Esa carpeta no se sube a Git. Luego:

```powershell
analysis\.venv\Scripts\python analysis\experimentos.py
```

Genera `analysis/salidas/experimentos.md`, las tablas `report/tablas/*.tex` (el informe las incluye solas) y las
gráficas `report/figuras/e1_jitter.pdf` y `e3_latencia.pdf`.

## Corriente con el tester USB

El tester USB se pone **entre** el cargador (5 V) y el cable del nodo. Muestra voltaje, corriente y mAh acumulados.
La corriente instantánea salta mucho (el Wi-Fi tiene picos), así que se usa el **promedio por energía**:

1. Anotar los mAh del tester al empezar (`mah_inicio`).
2. Dejar el nodo en el estado a medir **10 minutos**.
3. Anotar los mAh al terminar (`mah_fin`) y el voltaje.
4. Corriente promedio = (mah_fin − mah_inicio) / (minutos / 60).

Estados a medir:

| Estado | Cómo |
|---|---|
| ESP32 sola en reposo | Programa de prueba `boton_led` cargado, sin sensores |
| Nodo completo, FIFO + DMA, sin celular conectado | Firmware normal |
| Nodo completo con el celular en la página web | Wi-Fi con cliente |
| Cada modo de E1 | Los tres entornos |
| BME280/DHT22 + BH1750 conectados vs. desconectados | Aporte de los sensores de ambiente (se espera < 1 mA) |

Llenar `data/raw/nodo/corriente.csv`:

```csv
estado,minutos,mah_inicio,mah_fin,voltaje_v
nodo completo fifo_dma,10,0,0,5.05
```

(Los ceros son el formato: reemplazar con lo que muestre el tester.) Un power bank de 10 000 mAh a 5 V da
≈ 10 000 / corriente promedio horas (descontando pérdidas del convertidor, ~20 %).

## Estado (2-nov-2026)

El firmware que mide E1–E4 **compila** en los tres entornos. `analysis/experimentos.py` se probó con un archivo de
**EJEMPLO** inventado (`--ejemplo`, salida a una carpeta temporal). **No hay ninguna medición real todavía.**
