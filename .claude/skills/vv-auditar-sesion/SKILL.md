---
name: vv-auditar-sesion
description: Audita una sesión de campo de VÍA VIVA (CSV de sensores, GPS, hora, marcas, eventos, destellos, video) en solo lectura y separa hechos medidos de hipótesis. Úsala cuando llegue una sesión nueva de 06_CAMPO o de la Pi.
argument-hint: "<carpeta de sesión> [export crudo de phyphox para comparar]"
---

# Auditar una sesión de campo

Objetivo: decir si la sesión sirve para evaluar o calibrar, con cifras medidas. **Nunca modificar la carpeta original**:
es el dato crudo (`06_CAMPO`).

1. **Identificar la sesión.** Si `$ARGUMENTS` está vacío:
   - listar `06_CAMPO/sesiones/` con fecha, tamaño y `resumen.json`;
   - preguntar cuál auditar.
   - No suponer que todos los archivos de una carpeta son de la misma sesión: comprobar la hora con `bitacora.jsonl`
     y `meta/time.csv`.
2. **Auditoría base.** Desde la raíz del repo:
   `dataset\.venv\Scripts\python -m herramientas.auditar_sesion "<carpeta>" --json <scratchpad>\auditoria.json`.
   - Código 1 = hay FALLA.
   - Revisa: Hz, huecos, duplicados, 1 g en reposo, desfase entre acelerómetros, GPS, hora, marcas CSV/SQLite/vigentes,
     marcas contradictorias, destellos, minuto quieto y video.
3. **Si hay un export crudo de phyphox:** alinear por correlación cruzada de |a|. Esto comprueba que no se perdieron
   muestras y qué reloj estaba bien.
   - Hacerlo con un script en el scratchpad (`python -I -X utf8`, nombres con tilde NFD).
   - Comparar contra `meta/time.csv` del export: tramos START/PAUSE con la hora del iPhone.
4. **¿Las marcas sirven?** Ejecutar `python -m herramientas.comparar_detectores` sobre una **copia** sin video en el
   scratchpad:
   - TP/FP/FN de los dos detectores;
   - `repeticion_fiel`.
   - Hacen falta ≥ 2 sesiones reales con marcas revisadas para calibrar; con una sola, solo hay evaluación preliminar.
5. **Informe en el chat:**
   - sesión y rutas;
   - duración y registros;
   - FALLA y AVISO con su causa (verificada o hipótesis);
   - qué se puede entrenar o evaluar;
   - siguientes pasos.
   - **Sin coordenadas, placas ni datos personales.**

Reglas: no cambiar umbrales; no usar datos SINTÉTICOS como evidencia; no abrir `.env`. Lo que no se pudo medir se dice.
