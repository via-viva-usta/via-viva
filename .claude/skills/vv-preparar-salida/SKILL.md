---
name: vv-preparar-salida
description: Recorre la lista de verificación de docs/SALIDA_PI.md antes de una salida de campo con la Raspberry Pi (sensores, hora, espacio, prueba de mesa, auditoría y detectores) y dice qué está listo y qué falta.
argument-hint: "[carpeta de la prueba de mesa]"
disable-model-invocation: true
---

# Preparar la próxima salida

1. **Leer** `docs/SALIDA_PI.md`, sección A, y seguirla en orden. No inventar pasos.
2. **Comprobar dónde corre:**
   - En la Pi (`/proc/device-tree/model` contiene «Raspberry Pi»): ejecutar A1–A4 y mostrar la salida de cada uno.
   - En el PC: decir que A1–A4 se hacen en la Pi, y pasar los comandos exactos.
3. **Si `$ARGUMENTS` trae la carpeta de la prueba de mesa (A5):**
   - correr `python -m herramientas.auditar_sesion <carpeta>` (A6–A7);
   - correr `python -m herramientas.comparar_detectores <carpeta> --html <scratchpad>\mesa.html` (A8).
4. **Entregar una tabla A1–A9** con estado OK / FALTA / NO PROBADO y la evidencia de cada fila (comando y salida resumida).
   - Recordar B (foto del montaje) y C (tramo de control, marcar al pasar la rueda, destellos).

Reglas:
- No marcar OK nada que no se haya ejecutado.
- No copiar ni borrar datos de campo.
- No cambiar `viaviva/sensores.py` ni el firmware.
