---
name: vv-investigar-modelos
description: Busca repositorios, datasets, modelos o skills para la detección de eventos viales con sensores inerciales y los compara por datos, frecuencia, unidades, licencia, mantenimiento y compatibilidad con VÍA VIVA y la Pi 4. Solo lectura web; no descarga ni instala nada.
argument-hint: "[tema o candidato concreto]"
---

# Investigar modelos y datos externos

1. **Punto de partida:** `docs/INVESTIGACION_DETECTORES.md`, con la tabla del 19-nov. Solo buscar lo nuevo o lo que
   quedó «no verificado». Si `$ARGUMENTS` nombra un candidato, revisar solo ese.
2. **Para cada candidato, verificar en la página de origen**, nunca solo en un resumen de búsqueda:
   - enlace;
   - licencia: archivo LICENSE o ficha. Si no aparece, «no indicada»;
   - tamaño y procedencia;
   - sensor y montaje;
   - fs y unidades;
   - clases y cómo se etiquetaron (video, botón, inspección);
   - última actualización;
   - si es SINTÉTICO.
3. **Compatibilidad con VÍA VIVA:**
   - phyphox a 100 Hz en m/s² con gravedad;
   - ADXL345 a 200 Hz y MPU-6050 a 100 Hz;
   - GPS a 1 Hz;
   - clases hueco/resalto/tapa/grieta/parche/via_buena.
   - Indicar la conversión necesaria: g ↔ m/s², remuestreo, ejes.
4. **Tabla** con: candidato · qué aporta · datos/fs/unidades · licencia · mantenimiento · compatibilidad/Pi ·
   recomendación (evaluar / referencia / descartar).
5. **Antes de incorporar algo:** pedir aprobación a AC y revisar licencia, código y dependencias. Los datos externos
   no se suben a Git. Lo NC/ND no se redistribuye.

Una precisión medida con datos externos o sintéticos **no** es precisión en Tunja: decirlo siempre.
