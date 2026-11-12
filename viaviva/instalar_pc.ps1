# VÍA VIVA en un PC con Windows (una vez, con internet): crea viaviva\.venv con lo necesario para la captura,
# el tablero local, el detector y el dataset. Uso:  powershell -ExecutionPolicy Bypass -File viaviva\instalar_pc.ps1
# Los mensajes van sin tildes: Windows PowerShell 5.1 lee este archivo como ANSI.
$ErrorActionPreference = "Stop"
$raiz = Split-Path $PSScriptRoot -Parent
Set-Location $raiz

function Probar([string[]]$cmd) {
    # True si ese Python existe y es 3.11-3.13 (3.11 es el probado). Sin excepciones si no existe.
    $resto = @($cmd | Select-Object -Skip 1)
    try {
        & $cmd[0] @resto -c "import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)" 2>$null | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

# Primero el lanzador «py» (3.11, 3.12, 3.13); si no está, «python» del PATH.
$crear = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($v in "3.11", "3.12", "3.13") { if (Probar @("py", "-$v")) { $crear = @("py", "-$v"); break } }
}
if (-not $crear -and (Get-Command python -ErrorAction SilentlyContinue) -and (Probar @("python"))) { $crear = @("python") }
if (-not $crear) { throw "Falta Python 3.11 (o 3.12/3.13). Instalelo con:  winget install Python.Python.3.11  y abra otra consola." }
Write-Host "Python: $($crear -join ' ')"
$resto = @($crear | Select-Object -Skip 1)
& $crear[0] @resto -m venv viaviva\.venv
if ($LASTEXITCODE -ne 0) { throw "No se pudo crear viaviva\.venv" }
& viaviva\.venv\Scripts\python.exe -m pip install --upgrade pip
& viaviva\.venv\Scripts\python.exe -m pip install -r viaviva\requirements-pc.txt
if ($LASTEXITCODE -ne 0) { throw "pip no pudo instalar viaviva\requirements-pc.txt (hay internet?)" }
# .env sin secretos: la captura no necesita claves (Supabase y demas quedan vacios)
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Leaflet local: el tablero y la captura muestran el mapa aunque no haya internet en el carro
New-Item -ItemType Directory -Force viaviva\web\vendor\leaflet | Out-Null
foreach ($f in "leaflet.js", "leaflet.css") {
    try {
        Invoke-WebRequest "https://unpkg.com/leaflet@1.9.4/dist/$f" -OutFile "viaviva\web\vendor\leaflet\$f" -UseBasicParsing
    } catch { Write-Host "Aviso: no se descargo $f (el mapa usara la version simple)." -ForegroundColor Yellow }
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "Opcional: falta ffmpeg (solo para convertir videos HEVC del iPhone): winget install Gyan.FFmpeg" -ForegroundColor Yellow
}
Write-Host "`nListo. Prueba sin iPhone:  .\viaviva.cmd doctor --simulado ejemplo" -ForegroundColor Green
Write-Host "Practica de captura:      .\viaviva.cmd capture --replay ejemplo --por-http --abrir" -ForegroundColor Green
Write-Host "Salida de campo: doble clic en SALIDA_DE_CAMPO.cmd (pasos en README_SALIDA.md)" -ForegroundColor Green
