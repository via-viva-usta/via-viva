# Reconstruye la base de VÍA VIVA desde cero (Windows PowerShell 5 o PowerShell 7).
#
# Uso, desde la carpeta via-viva\:
#   powershell -ExecutionPolicy Bypass -File db\reconstruir.ps1            # crea el entorno si falta y corre todo
#   powershell -ExecutionPolicy Bypass -File db\reconstruir.ps1 -Limpiar   # borra la base antes de empezar
#
# Necesita Python 3.11 (py -3.11) e internet (OpenStreetMap, datos.gov.co, OpenTopoData).
param(
    [switch]$Limpiar,
    [switch]$SinEntorno   # no crea ni actualiza etl\.venv (si ya está listo)
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$inicio = Get-Date

function Paso([string]$titulo, [string[]]$argumentos) {
    Write-Host "`n=== $titulo ===" -ForegroundColor Cyan
    & $script:py @argumentos
    if ($LASTEXITCODE -ne 0) { throw "Falló: $titulo (código $LASTEXITCODE)" }
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Se creó .env a partir de .env.example"
}

if (-not $SinEntorno) {
    if (-not (Test-Path "etl\.venv\Scripts\python.exe")) {
        Write-Host "Creando el entorno virtual etl\.venv ..."
        py -3.11 -m venv etl\.venv
        if ($LASTEXITCODE -ne 0) { throw "No se pudo crear etl\.venv (¿está instalado Python 3.11?)" }
    }
    & etl\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
    & etl\.venv\Scripts\python.exe -m pip install --quiet -r risk_model\requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Falló pip install" }
}
$script:py = (Resolve-Path "etl\.venv\Scripts\python.exe").Path
$env:PYTHONIOENCODING = "utf-8"

if ($Limpiar) {
    $ruta = & $script:py -c "from db.acceso import ruta_sqlite; print(ruta_sqlite())"
    if (Test-Path $ruta) { Remove-Item $ruta; Write-Host "Base anterior borrada: $ruta" }
}

Paso "1/7 Esquema (db/schema.sql)"                    @("-m", "db.acceso")
Paso "2/7 Grafo de calles de Tunja (OpenStreetMap)"   @("-m", "etl.osm_tunja")
Paso "3/7 Barrios y veredas (Alcaldía, datos abiertos)" @("-m", "etl.barrios_tunja")
Paso "4/7 Elevación y pendiente (SRTM 30 m)"          @("-m", "etl.elevacion")
Paso "5/7 Lluvia diaria IDEAM (últimos 30 días)"      @("-m", "etl.scraping.clima_ideam")
Paso "6/7 Noticias de cierres y accidentes"           @("-m", "etl.scraping.noticias")
Paso "7/7 Tabla de variables por tramo"               @("-m", "risk_model.variables")

Write-Host "`n=== Resumen ===" -ForegroundColor Green
& $script:py -m db.acceso
Write-Host ("Tiempo total: {0:N0} s" -f ((Get-Date) - $inicio).TotalSeconds)
