# ¿Por qué la Raspberry Pi 4 es el nodo central y el ESP32 la línea base? (nota para Arquitectura, R7)

**Decisión del 7-nov-2026:** el docente de Arquitectura consideró insuficiente el ESP32 como nodo central. La Pi 4
pasa a ser el nodo; el ESP32 sale del camino crítico y se conserva (`firmware/`) como **línea base de comparación**.
La nota anterior (Pi solo como servidor opcional) quedó en `docs/archivo/futuro_pi_2026-11-07/`.

## Lo que ya está medido (7-nov, en el PC; `pi/r7/benchmark_cnn.py`)

| Hecho | Valor | Consecuencia |
|---|---|---|
| Activaciones de MobileNetV2 int8 (224 × 224) | ≥ 1 470 KB | El ESP32 tiene 520 KB de SRAM (~300 KB libres con el firmware): **no cabe** |
| Tamaño de MobileNetV2 int8 | 2 647 KB | La partición de la app deja ~1 MB libre: **no cabe en flash** |
| MobileNetV3-Small int8 | 1 182 KB; activaciones ≥ 392 KB | Tampoco cabe |
| Red 1D int8 del nodo | 788 parámetros, 872 B | Cabe: es la que el ESP32 sí puede correr (E3) |

## Qué gana el sistema con la Pi 4 (y qué cuesta)

| Gana | Cuesta / se mitiga con |
|---|---|
| Un solo equipo hace sensores + base local + aplicativo web para el celular, la tablet y la Alcaldía | Linux no es de tiempo real → la **FIFO del ADXL345** (32 muestras = 160 ms a 200 Hz) es el colchón; se cuentan los desbordes |
| La misma CNN int8 de fotos puede correr en el nodo (benchmark de R7) | Más consumo que el ESP32 → se mide con el tester USB (`pi/r7/tabla_r7.py consumo`) |
| SQLite completa como fuente de verdad, exportables (PDF/Excel) y sincronización sin el portátil | microSD frágil ante cortes → **apagado seguro** con el pulsador y fsync al cerrar cada grabación |
| Python en todo el sistema: el detector es el mismo código probado con phyphox | Arranca más lento que el ESP32 ([PENDIENTE: medir el tiempo de arranque]): el servicio systemd arranca solo al encender el carro |

## Qué se compara en R7 (misma tabla, media ± desviación con Welford, n ≥ 100)

ESP32 (línea base, mediciones de `firmware/` E1–E4) vs. Raspberry Pi 4 (`data/logs/r7_pi.jsonl`) vs. celular
(`web/clasificador/`): latencia del detector, adquisición (DMA ping-pong vs. FIFO + interrupción), % CPU, RAM,
temperatura, consumo y CNN de fotos. Resultados de la Pi: [PENDIENTE: medición en la placa].
