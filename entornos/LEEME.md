# entornos/ — versiones exactas de cada venv (reproducibilidad)

`pip freeze` del 7-nov-2026 en el PC de Andrés (Windows 11, Python 3.11). Los `requirements.txt` de cada carpeta dicen
qué se necesita; estos archivos dicen **exactamente** qué versión estaba instalada cuando todo funcionó.

| Archivo | Venv | Reproducir |
|---|---|---|
| `etl.txt` | `etl\.venv` (ETL + modelo de riesgo) | `py -3.11 -m venv etl\.venv; etl\.venv\Scripts\python -m pip install -r entornos\etl.txt` |
| `analysis.txt` | `analysis\.venv` (detector del nodo, PyTorch CPU) | igual, con `analysis` |
| `bot.txt` | `bot\.venv` (bot + LiteRT) | igual, con `bot` |
| `dataset.txt` | `dataset\.venv` (fotos, captura en vivo, validador, pytest) | igual, con `dataset` |
| `vv-modelo.txt` | `%USERPROFILE%\.venvs\vv-modelo` (TensorFlow 2.20, tf_keras, tfmot) | `py -3.11 -m venv $env:USERPROFILE\.venvs\vv-modelo` y `pip install -r entornos\vv-modelo.txt` |

Actualizar después de instalar algo: `<venv>\Scripts\python -m pip freeze > entornos\<venv>.txt` (conservar las 2
líneas de encabezado). Seguridad: `python -m herramientas.buscar_secretos` revisa todo el historial de Git.
