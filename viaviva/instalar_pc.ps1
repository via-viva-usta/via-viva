# VÍA VIVA en un PC con Windows (una vez, con internet): crea viaviva\.venv con lo necesario para la captura,
# el tablero local, el detector y el dataset. Uso:  powershell -ExecutionPolicy Bypass -File viaviva\instalar_pc.ps1
$ErrorActionPreference = "Stop"
$raiz = Split-Path $PSScriptRoot -Parent
Set-Location $raiz
$py = (Get-Command py -ErrorAction SilentlyContinue)
if (-not $py) { throw "Falta Python 3.11: winget install Python.Python.3.11" }
py -3.11 -m venv viaviva\.venv
& viaviva\.venv\Scripts\python.exe -m pip install --upgrade pip
& viaviva\.venv\Scripts\python.exe -m pip install -r viaviva\requirements-pc.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Write-Host "`nListo. Prueba sin iPhone:  .\viaviva.cmd doctor --simulado <export de phyphox .zip>" -ForegroundColor Green
Write-Host "Salida de campo: doble clic en SALIDA_DE_CAMPO.cmd (pasos en README_SALIDA.md)" -ForegroundColor Green
