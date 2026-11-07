# Revisión técnica y tareas para Claude Code — 7-nov-2026

Este archivo recoge una revisión estática del repositorio y prioridades para los últimos días antes de la entrega del 13-nov. No sustituye pruebas con hardware, revisión del equipo ni aprobación de licencias. La revisión no ejecutó la suite ni compiló el firmware.

## Estado observado

- La copia local está en `main`, alineada con `origin/main`, último commit observado `63c6212` (5-nov-2026); al iniciar la revisión no había cambios locales pendientes.
- `docs/ESTADO.md` y `CLAUDE.md` están fechados 5-nov. Reportan 0 recorridos y 0 fotos de campo, falta de pruebas con hardware real, prueba del clasificador en iPhone y prueba de extremo a extremo con Telegram. **Actualizar esos datos antes de afirmar que siguen vigentes.**
- `data/` contiene directorios locales ignorados por Git (`raw/`, `campo/`, `externo/`, `osm/`, `procesado_sintetico/`) y dos bases SQLite. El mero conteo de archivos no permite distinguir material real de sintético; confirmar procedencia y consentimiento localmente antes de procesar o mostrar resultados.
- La arquitectura abarca firmware ESP32, Python (ETL, análisis, dataset, riesgo y bot), SQLite, mapa Leaflet y tablero Java. Hay cinco módulos de prueba pytest y workflows para Python y firmware, pero esta revisión no comprobó sus resultados actuales.
- `dataset/externos.py` descargaba el ZIP de Kaggle y llamaba a `extractall` sin validar los nombres de archivo internos. Se añadió extracción segura que rechaza rutas absolutas, `..`, rutas con unidad de Windows y enlaces simbólicos, y comprueba todos los miembros antes de escribir. **Pendiente de ejecutar pruebas de regresión** (ZIP válido, `../escape`, ruta Windows absoluta, enlace simbólico y ZIP malformado).
- En el firmware, la lectura FIFO del ADXL345 encolaba transacciones DMA de 7 bytes usando buffers con stride de 7. La [guía oficial de ESP-IDF](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/spi_master.html) exige buffers DMA alineados a 32 bits y longitud múltiplo de 4 bytes; por tanto esas lecturas no cumplían el contrato del driver. Se cambió a transacciones de 8 bytes con stride de 8 (se consumen los 6 bytes de datos; el byte adicional es descartado). Ahora también se comprueban fallos del lote, se drenan las transacciones encoladas y se descarta el lote fallido. **Pendiente compilar con PlatformIO y comprobar los datos del sensor real** antes de considerar resuelto en funcionamiento.

## Prioridades recomendadas

### P0 — Antes de presentar o publicar

1. Actualizar `docs/ESTADO.md`, `CLAUDE.md`, `README.md`, demo e informe con una matriz honesta de probado / no probado y con el origen real o sintético de cada dato mostrado.
2. Probar el recorrido de campo real de principio a fin: validador → conversión de etiquetas → ingesta → eventos/tramos → exportación de mapa/tablero. Registrar errores y no inventar métricas si aún no hay suficientes etiquetas.
3. Con hardware disponible, probar cada sensor y luego sesiones largas: SD, GPS, interrupción/FIFO, reinicios, watchdog, descarga Wi-Fi y pérdidas de muestras. La compilación no demuestra el funcionamiento en placa.
4. Compilar los tres entornos de PlatformIO tras el cambio DMA; comprobar secuencias plausibles de aceleración/contadores FIFO en el ADXL345 real; luego probar clasificador en el iPhone, bot con Telegram real y demo PowerShell en una máquina limpia. Confirmar que el mapa DEMO no se confunda con datos de campo.
5. Revisar publicación/privacidad: no subir `data/`, fotos originales, datos de Alcaldía, coordenadas identificables ni secretos. Resolver antes el difuminado de imágenes de reportes del bot o excluir las fotos de la demo.

### P1 — Calidad del software, cuando P0 esté estable

- Añadir casos de prueba para la extracción segura incorporada en `dataset/externos.py`; revisar también validación de coordenadas/cajas XML y YOLO, recortes vacíos y duplicados al reejecutar.
- Confirmar que la transacción DMA de 8 bytes del ADXL345 mantiene la cadencia de 200 Hz y que el byte de relleno no produce pérdida de muestra en FIFO; medir pérdidas y overrun durante una sesión prolongada.
- Comparar de forma reproducible el detector por umbrales con el modelo usando división por recorrido, matriz de confusión, precisión/recobrado y latencia; separar alertas por bache de resaltos/manholes y otros eventos.
- Revisar consistencia entre firmware y Python para unidades, tiempo, orientación y versión de modelo; incluir versión/configuración del detector en cada sesión CSV.
- Revisar límites y casos de error de SQLite y exportación web (base ausente, datos corruptos, eventos sin coordenadas, consulta grande), además de los estados del reporte.
- Verificar lista de dependencias, licencias de código/modelos/datos, instalación reproducible y CI. Mantener datasets y binarios grandes fuera de Git.

### P2 — No introducir en esta entrega salvo necesidad confirmada

- Backend/API persistente y sincronización en línea; migración a PostgreSQL/PostGIS; automatización de publicación; nuevo modelo de visión o fusión multimodal; nuevas placas/sensores. Son mejoras de siguiente iteración, no reemplazan los datos y las pruebas faltantes.

## Fuentes externas investigadas (candidatas, no incorporadas)

La revisión fue una búsqueda inicial, no un inventario exhaustivo de todos los repositorios públicos. No se descargaron datasets ni se clonaron repositorios.

| Fuente | Qué aporta | Uso posible y límites |
|---|---|---|
| [Kaggle: andrewmvd/pothole-detection](https://www.kaggle.com/datasets/andrewmvd/pothole-detection) | Dataset ya descrito en `docs/datasets_externos.md`: imágenes de baches con cajas VOC; allí se anota DbCL v1.0 y 665 imágenes. | Útil solo como preentrenamiento auxiliar según el protocolo existente; comprobar licencia/citación de la versión al descargar. No usar para evaluar generalización en Tunja.
| [Kaggle: Pothole Image Data-Set](https://www.kaggle.com/datasets/sachinpatel21/pothole-image-dataset) | La ficha indica 600+ imágenes raspadas de Google, posible ruido/duplicados y licencia CC0. | Candidato de menor confianza: falta revisar derechos/procedencia de cada imagen, anotaciones y calidad. No añadir al entrenamiento sin revisión legal y de duplicados.
| [GitHub: PaveTrack object detection](https://github.com/large-road-damage-datalake/pavetrack-object-detection) y [registro Science Data Bank](https://www.scidb.cn/en/detail?dataSetId=e9ffbca43e6e4a5ebdd25663d0de9ad1) | Repositorio declara 46.124 imágenes, 176.243 cajas, 11 clases y separación por países; licencia apunta al registro original. | Interesante para grietas, resaltos y variedad de daños; dataset grande y licencia debe verificarse en el registro fuente antes de descargar/usar. No copiar todo el repositorio al proyecto.
| [GitHub: Pothole Detection Lab](https://github.com/warstad11/pothole) | Ejemplo de evaluación multimodal (cámara + acelerómetro) y protocolo ciego de transferencia; incluye advertencias de caída de rendimiento real. | Leer metodología y adaptar controles contra fuga y sesgo. El proyecto es MIT, pero el propio repo indica que datasets incluidos/referenciados tienen licencias separadas; no importar sus datos/modelos automáticamente.

## Acceso y datos que faltan

- El perfil comprobado no tiene `~/.kaggle/kaggle.json`; tampoco se detectó un ejecutable `kaggle` en PATH. Para descargar de Kaggle, el usuario debe instalar/configurar el cliente oficial y aceptar las condiciones en su cuenta, o poner el token en el perfil local. **No pegar tokens en el chat ni en Git.** Después se puede ejecutar `python -m dataset.externos --descargar-kaggle` desde el repo.
- No se inició sesión en Kaggle ni se modificaron cuentas. Los repositorios públicos de GitHub se pudieron consultar en web, pero no se clonaron por la restricción de red de esta sesión.
- Para completar la parte de datos hacen falta: (1) confirmar cuáles CSV/fotos en `data/raw` son datos reales autorizados y cuáles sintéticos; (2) que el equipo disponga de token Kaggle local; (3) resultados de placa/iPhone/Telegram o que conecten esos equipos para capturarlos.

## Mensaje listo para compartir con Claude Code

> Lee `docs/REVISION_TECNICA_2026-11-07.md`. No afirmes que el proyecto está validado solo porque compile. Primero actualiza `docs/ESTADO.md` con evidencia de los recorridos/fotos ya recibidos, clasifícalos como reales o sintéticos y ejecuta el flujo de campo sobre datos reales autorizados. Para cada paso que no pueda probarse (hardware, iPhone, Telegram), déjalo explícito. Revisa los cambios nuevos: `extraer_zip_seguro` en `dataset/externos.py` y el stride/transacción de 8 bytes para DMA del ADXL345 en `firmware/nodo-sensores/src/adxl345.{h,cpp}`. Agrega pruebas de regresión para ZIP válido y entradas maliciosas, compila todos los entornos PlatformIO y confirma el DMA con el sensor real. No subas ni publiques fotos, datos crudos/Alcaldía, secretos ni resultados sintéticos presentados como reales. Revisa las fuentes externas listadas aquí; no descargues ni mezcles datasets hasta verificar licencia, procedencia y consentimiento. Haz cambios pequeños en una rama y reporta archivos, comandos ejecutados, resultados y pendientes; no publiques ni hagas push sin autorización.
