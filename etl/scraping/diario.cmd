@echo off
rem VÍA VIVA - scraping diario (lo llama el Programador de tareas; ver herramientas\programar_scraping.ps1).
rem Se ubica en la carpeta via-viva y usa el venv del ETL. La salida de consola queda en data\logs\scraping_diario.txt.
cd /d "%~dp0..\.."
if not exist "data\logs" mkdir "data\logs"
set PYTHONIOENCODING=utf-8
"etl\.venv\Scripts\python.exe" -m etl.scraping.diario >> "data\logs\scraping_diario.txt" 2>&1
