---
name: vv-comparar-detectores
description: Compara el detector en vivo (nucleo.py) y el de análisis (detector.py + config/detector.yaml) sobre las mismas sesiones y marcas, con la misma tolerancia, y genera un HTML para revisar desacuerdos. Úsala antes de tocar umbrales o unificar detectores.
argument-hint: "<sesiones o exports…> [--sensor adxl2|mpu6050]"
---

# Comparar los dos detectores

1. **Elegir las sesiones** de `$ARGUMENTS`.
   - Por defecto: las sesiones reales de `06_CAMPO/sesiones/` (no las de `origen: simulado`) y los exports de
     `06_CAMPO/phyphox/`.
   - Trabajar sobre **copias** sin video en el scratchpad.
2. **Correr:**
   `dataset\.venv\Scripts\python -m herramientas.comparar_detectores <rutas> --html <scratchpad>\comparacion.html --json <scratchpad>\comparacion.json`.
   - Con la Pi, repetir con `--sensor adxl2` y `--sensor mpu6050` para ver si los sensores discrepan.
3. **Comprobar `repeticion_fiel`:** debe repetir todos los eventos de `eventos.csv`. Si no, la comparación no es válida:
   revisar la velocidad del GPS y la fs antes de seguir.
4. **Informe:** una tabla por sesión con eventos, TP, FP, FN, P, R y F1 de cada detector, coincidencias entre ellos y
   aciertos por clase.
   - Abrir el HTML (SendUserFile, `display: render`) y señalar 3–5 desacuerdos concretos: segundo y qué se ve.
5. **Decisión de umbrales, solo con datos:**
   - ≥ 2 salidas reales con marcas **revisadas con video**;
   - calibración dejando una salida afuera (`viaviva detector calibrar`);
   - márgenes elegidos sobre la curva P/R de las salidas de validación, no sobre la de entrenamiento.
   - Si no se cumple, decirlo y no proponer números.

Diferencias conocidas:
- **En vivo:** |a| − 1 g; pico a pico en 50 ms > 6 × RMS de fondo y > 0,30 g; refractario de 1 s.
- **Análisis:** eje vertical por gravedad; pico en 0,2 s normalizado por velocidad > 0,35 g, > 4 × fondo y jerk
  > 12 g/s, las tres a la vez.

Las dos versiones siguen sin calibrar.
