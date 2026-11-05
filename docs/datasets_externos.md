# Datasets externos de baches (revisión del 5-nov-2026)

Los compartió Dany. Se revisaron **antes** de usarlos: contenido, licencia, calidad, fuga con nuestras fotos y para qué
sirven. Las imágenes van en `data/externo/` (ignorada por Git) y **nunca** se mezclan con el dataset de Tunja: la
evaluación final del clasificador es SIEMPRE con nuestras fotos y división por sitio.

| | Kaggle `andrewmvd/pothole-detection` | Hugging Face `Duranishhh/baches-carreteras` |
|---|---|---|
| Contenido | **665 imágenes**, anotaciones con recuadros en **PASCAL VOC** (un `.xml` por imagen) | **4.719 imágenes**, **7.340** baches con recuadros (YOLO `.txt` + `metadata.jsonl` estilo COCO); train 3.281 / val 720 / test 718 |
| Clases | 1: `pothole` | 1: `0` = bache |
| Tamaño | 350,98 MB (versión 1) | 86 % de 640 × 640 px; 9.443 archivos |
| Origen | "Potholes Dataset" de MakeML (republicado por Larxel en Kaggle) | Copia reorganizada del repo de GitHub de Bisman-Singh-Dev (2026, versión `bd8238b`): **mezcla de imágenes reales y sintéticas** de varias fuentes |
| **Licencia** | **Database Contents License (DbCL) v1.0** (Open Data Commons) | Ficha: `license: other`, nombre literal **"licencia-de-imagenes-no-documentada"**; el repo de origen declara MIT **solo para el código** |
| Problemas conocidos | Sin imágenes "sin bache" (todas positivas); procedencia de cada foto según MakeML (no detallada) | Según su propia ficha: solo 22 imágenes sin baches (0,5 %); **48 de 718 imágenes de test (6,7 %) casi repetidas en train** y 13 grupos de archivos idénticos |
| Fuga con nuestras fotos | Ninguna esperable (no son de Tunja); se verificará con dHash al descargar | — |
| **Decisión** | **Usable con fines académicos citando la fuente.** Sirve para (1) **pre-entrenar** una tarea auxiliar hueco / no-hueco (recortes dentro y fuera de los recuadros), (2) un **detector con recuadros** si hubiera tiempo, (3) comparar. **Pendiente: descargarlo** (falta `kaggle.json`) | **NO se usa**: licencia de las imágenes no clara y contiene imágenes sintéticas de origen no trazable. Solo se puede mencionar como trabajo relacionado |

## Cómo se cita (Kaggle)

> Make ML. *Potholes Dataset*. https://makeml.app/datasets/potholes. Republicado como "Pothole Detection" por Larxel
> (andrewmvd) en Kaggle: https://www.kaggle.com/datasets/andrewmvd/pothole-detection. Licencia DbCL v1.0.

## Cómo descargarlo y revisarlo (cuando exista `C:\Users\AC\.kaggle\kaggle.json`)

1. Kaggle → *Settings* → *API* → *Create New Token*: descarga `kaggle.json`; guardarlo en `C:\Users\AC\.kaggle\`
   (nunca en el repo ni en el chat).
2. Descargar y revisar (conteos, tamaños, recuadros, duplicados por dHash y posible fuga con `data/raw/fotos`):

```powershell
dataset\.venv\Scripts\python -m pip install kaggle
dataset\.venv\Scripts\python -m dataset.externos --descargar-kaggle
dataset\.venv\Scripts\python -m dataset.externos --revisar data\externo\kaggle_potholes
```

3. Si la revisión es buena, el pre-entrenamiento lo usa con `dataset.modelo --preentrenar data\externo\kaggle_potholes`.

## Estado

- Kaggle: **revisado por su ficha pública**; descarga y revisión de calidad **pendientes** (faltan credenciales).
- Hugging Face: **descartado** por licencia (no se descargaron las imágenes; los datos de arriba son de su ficha).
