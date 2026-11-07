# ¿Por qué una Raspberry Pi 4 no es sobredimensionar? (nota para Arquitectura, R7)

La Raspberry Pi 4 **no está en la lista de los lineamientos** del Proyecto Integrador. Por eso no se agrega por
gusto: entra solo si una **medición** muestra que hace algo que el ESP32 no puede, y sin tocar el núcleo del nodo.

## Lo que ya está medido (7-nov, en el PC; script `benchmark_cnn.py`)

| Hecho | Valor | Consecuencia |
|---|---|---|
| Memoria de activaciones de MobileNetV2 int8 (224 × 224) | ≥ 1 470 KB | El ESP32 tiene 520 KB de SRAM, ~300 KB libres con el firmware: **no cabe** |
| Tamaño del modelo MobileNetV2 int8 | 2 647 KB | La partición de la app deja ~1 MB libre: **no cabe en flash** |
| MobileNetV3-Small int8 | 1 182 KB; activaciones ≥ 392 KB | Tampoco cabe (y en int8 perdía exactitud en la prueba sintética) |
| Red 1D int8 del nodo | 788 parámetros, 872 B | Sí cabe: es la que corre en el ESP32 (E3) |

Conclusión: **la CNN de fotos no puede correr en el ESP32**. Por eso las imágenes van al celular (dispositivo de borde
para imágenes, decisión del 3-nov) y el ESP32 se queda con la señal del acelerómetro. Eso no cambia.

## Para qué serviría la Pi 4 (y para qué no)

| Sí | No |
|---|---|
| Servidor 24/7 del bot y del scraping diario, sin el portátil prendido (consumo de unos pocos vatios) | Reemplazar al ESP32 en el carro (más consumo, arranque lento, microSD frágil ante cortes) |
| Tercer punto de la comparación de R7: misma CNN int8 en ESP32 (no cabe) vs. Pi 4 vs. celular | Cámara a bordo (la evidencia la toma el celular) |

## Criterio de decisión (antes de comprarla o usarla)

1. Medir en la Pi 4 con `benchmark_cnn.py` (latencia media ± desviación, RAM, energía por inferencia con el tester USB).
2. Si la Pi no aporta frente al celular (misma latencia o peor) **y** el portátil alcanza como servidor para la demo,
   la Pi queda solo como dato de comparación en el informe, no en el sistema.
3. Especificaciones pendientes de anotar: RAM, cámara, fuente y microSD (`README.md`).

Resultados de la Pi: [PENDIENTE: medición en la placa].
