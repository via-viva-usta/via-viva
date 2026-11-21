# Salida de campo con la Raspberry Pi 4 — lista de verificación

Para la primera salida con la Pi y sus sensores. La guía con phyphox sigue en `README_SALIDA.md`.

**Antecedente:** la salida del 18-nov (iPhone A con phyphox) **no sirve como calibración**.
- La hora de eventos y marcas quedó corrida +2 109 s (PR #56).
- Las marcas casi no coinciden con golpes medibles.
- Los dos detectores dieron 74 y 8 eventos sobre la misma señal.

Esta salida busca **datos comparables**, no ajustar umbrales.

Ninguna parte de esta lista se ha probado todavía en la Pi real. Si un paso falla, se anota tal cual; no se inventa el
resultado.

## A. El día antes (en la mesa, con la Pi encendida)

| # | Qué | Cómo | Se acepta si |
|---|---|---|---|
| A1 | Sensores y pines | `bash herramientas/pi_probar.sh` (PR #41) | 0 FALLA. Cada sensor montado aparece OK |
| A2 | Pre-chequeo de la app | `viaviva/.venv/bin/python -m viaviva doctor --source pi` | LISTO |
| A3 | Espacio | `df -h /` | ≥ 5 GB libres. Por acelerómetro, 30 min a 200 Hz dan ≈ 20 MB de CSV (estimado con los ~59 B por fila del export del 18-nov) |
| A4 | Hora | `timedatectl` con internet. Sin internet, la app toma la hora del GPS y lo avisa en la bitácora | `System clock synchronized: yes`, o el aviso «Hora corregida con el GPS» |
| A5 | Prueba de mesa de 3 min | Grabar; 3 golpes secos con el dedo sobre la caja, separados 10 s; 1 marca de cada clase; 1 deshacer; 2 destellos (`/sync`); detener | — |
| A6 | Auditar la prueba de mesa | `python -m herramientas.auditar_sesion <carpeta>` | **0 FALLA**: hora = reloj del equipo (±2 s), sin huecos, 1 g en reposo, marcas en CSV = SQLite |
| A7 | Sensores entre sí | Mismo informe, «frente al principal» | Los 3 golpes aparecen en cada acelerómetro. Desfase ≤ 20 ms y r ≥ 0,5. Si no, revisar el montaje o la hora de lectura |
| A8 | Detectores con la misma señal | `python -m herramientas.comparar_detectores <carpeta> --html mesa.html` | `repeticion_fiel` = eventos de `eventos.csv`. Los golpes se ven en las dos pistas |
| A9 | Respaldo | Copiar la tarjeta o la carpeta de sesiones a otro disco | Copia verificada antes de salir |

## B. Montaje (foto obligatoria antes de arrancar)

- ADXL345 #1, ADXL345 #2 y MPU-6050 van en la **misma caja**, rígida y atornillada (no con velcro). Anotar en la foto
  la flecha de cada eje.
- La caja va siempre en el mismo sitio del carro. Anotar el carro, quién maneja y la presión de las llantas si se sabe.
- La antena GPS debe tener cielo a la vista. Los cables no deben moverse con la vibración.

## C. En la salida

1. **1 minuto quieto** con el motor encendido. Destello en `/sync` frente a la cámara del iPhone B.
2. **Tramo de control** (5–10 min, 3 vueltas): una calle con 2–3 resaltos y huecos conocidos, a ~15 y ~25 km/h.
   - Es la referencia repetible para comparar sensores y detectores entre salidas.
   - En cada vuelta, marcar los mismos puntos.
3. Recorrido libre.
   - Marcar **cuando la rueda pasa** sobre el defecto, no al verlo.
     - El 18-nov, en resaltos y tapas, el golpe llegó ~1,3 s después de la marca.
   - `via_buena` cada ~2 min en tramos lisos: son los negativos.
   - Grieta y parche solo si la rueda los pisa.
4. **Al final:** destello frente a la cámara y 1 minuto quieto. Detener la grabación antes de apagar. El pulsador de
   GPIO27 apaga limpio.
5. No pausar ni reiniciar la captura a mitad de camino. Si pasa, anotar la hora.

## D. Al volver (el mismo día)

1. Copiar la carpeta de la sesión **sin abrirla con otros programas**. Es el dato crudo: no se edita.
2. `python -m herramientas.auditar_sesion <carpeta> --json auditoria.json`: guardar el resultado junto a la copia, fuera de
   Git.
3. Importar el video del iPhone B en **Sesiones**. Debe sincronizarse por **destello**, no a mano.
4. En **Revisión**, confirmar o corregir cada marca mirando el video. Solo las marcas revisadas cuentan para calibrar.
5. `python -m herramientas.comparar_detectores <carpeta> --html comparacion.html`. Revisar a ojo los desacuerdos:
   - eventos de un solo detector;
   - marcas sin evento;
   - sensores que no ven el mismo golpe.

## Qué NO se hace con estos datos

- No se fijan umbrales con una sola salida. La calibración pide ≥ 2 salidas reales con marcas revisadas
  (`viaviva detector calibrar`, dejando una salida afuera).
- No se reporta precisión con datos SINTÉTICOS ni con la salida del 18-nov.
- No se suben a Git datos, videos ni coordenadas.
