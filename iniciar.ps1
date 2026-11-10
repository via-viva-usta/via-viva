# VÍA VIVA — todo en un comando en el PC (PowerShell, desde la carpeta via-viva). En la Raspberry Pi lo arranca
# systemd (viaviva/instalar.sh); este script es para la demo y el desarrollo en Windows.
#
#   .\iniciar.ps1                       base real (o DEMO si no tiene datos) + servidor de la Pi + mapa + clasificador
#   .\iniciar.ps1 -Demo                 fuerza la base DEMO (data\via_viva_demo.db, datos marcados DEMO)
#   .\iniciar.ps1 -Reproducir data\raw\phyphox\2026-11-07_03_pipe.zip   el servidor de la Pi REPRODUCE una grabación
#   .\iniciar.ps1 -Phyphox http://172.20.10.1:8080                       + captura en vivo desde el iPhone (phyphox)
#   .\iniciar.ps1 -ConTablero -SinCelular
#
# Levanta en orden: (1) base, (2) servidor de la Pi (captura + tablero de la Alcaldía) en http://localhost:8081,
# (3) mapa web estático, (4) tablero Java (solo con -ConTablero), (5) clasificador para el celular, (6) captura de
# phyphox (si se pide). El bot de Telegram quedó pospuesto en futuro\bot (7-nov). Guion: docs\demo.md.
param([switch]$Demo, [switch]$ConTablero, [switch]$SinCelular, [string]$Reproducir = "", [string]$Phyphox = "")
$ErrorActionPreference = "Stop"
$raiz = $PSScriptRoot
Set-Location $raiz
$env:PYTHONIOENCODING = "utf-8"
$etl = Join-Path $raiz "etl\.venv\Scripts\python.exe"
$dat = Join-Path $raiz "dataset\.venv\Scripts\python.exe"
function Paso($t) { Write-Host "`n== $t" -ForegroundColor Yellow }

# 1. Base: real o DEMO
Paso "1/6 Base de datos"
$real = Join-Path $raiz "data\via_viva.db"
$hayDatos = & $etl -c "import sqlite3;c=sqlite3.connect(r'$real');print(c.execute('select (select count(*) from eventos where origen!=''simulado'')+(select count(*) from reportes)').fetchone()[0])"
if ($Demo -or [int]$hayDatos -eq 0) {
    Write-Host "Sin datos reales (o -Demo): se usa la base DEMO; todo lo que se vea queda marcado DEMO." -ForegroundColor Red
    & $etl demo\datos_demo.py
    $env:VIA_VIVA_DB_URL = "sqlite:///data/via_viva_demo.db"
    & $etl -m risk_model.variables | Out-Null
    & $etl -m risk_model.modelo --demo-sintetico --guardar | Select-Object -Last 3
    $base = Join-Path $raiz "data\via_viva_demo.db"
} else {
    $env:VIA_VIVA_DB_URL = "sqlite:///data/via_viva.db"
    $base = $real
    Write-Host "Base real: $hayDatos eventos/reportes."
}

# 2. Servidor de la Pi (el mismo código que corre en la Raspberry). En el PC no hay sensores: sin -Reproducir
#    queda solo el tablero; con -Reproducir la página de captura muestra la grabación como si fuera el carro.
Paso "2/6 Servidor VÍA VIVA (captura + tablero de la Alcaldía)"
$argsPi = @("-m", "pi.servidor", "--puerto", "8081", "--sin-sync")
if ($Reproducir) { $argsPi += @("--fuente", "reproducir", "--archivo", "`"$Reproducir`"", "--bucle") }
Start-Process $dat -ArgumentList $argsPi
Start-Sleep -Seconds 3
Start-Process "http://localhost:8081/tablero"
if ($Reproducir) { Start-Process "http://localhost:8081/" }

# 3. Mapa web (estático, ciudadanía): http://localhost:8080
Paso "3/6 Mapa web"
& $etl web\exportar.py
Start-Process $etl -ArgumentList "-m", "http.server", "8080", "--directory", "web"

# 4. Tablero Java (Estructuras de Datos; las mismas estructuras están en viaviva\estructuras.py)
if ($ConTablero) {
    Paso "4/6 Tablero Java"
    $jar = Join-Path $raiz "dashboard-java\dist\TableroViaViva.jar"
    if (-not (Test-Path $jar)) {
        $ant = "C:\Program Files\NetBeans-25\netbeans\extide\ant\bin\ant.bat"
        $copy = "C:\Program Files\NetBeans-25\netbeans\java\ant\extra\org-netbeans-modules-java-j2seproject-copylibstask.jar"
        & $ant -q -f dashboard-java\build.xml "-Dlibs.CopyLibs.classpath=$copy" jar
    }
    Start-Process java -ArgumentList "-jar", "`"$jar`"", "`"$base`""
}

# 5. Clasificador en el celular (TFLite en el navegador, mismo WiFi)
if (-not $SinCelular) {
    Paso "5/6 Clasificador para el celular"
    if (Test-Path (Join-Path $raiz "dataset\salidas\ultimo.txt")) {
        Start-Process $etl -ArgumentList "web\clasificador\preparar.py", "--servir"
        Write-Host "Ver la URL en la ventana nueva y abrirla en el iPhone (mismo WiFi)."
    } else { Write-Host "No hay modelo de fotos (dataset\salidas): entrenar con dataset.modelo." -ForegroundColor Red }
}

# 6. Captura en vivo de phyphox (iPhone por el acceso remoto): respaldo si la Pi no está
if ($Phyphox) {
    Paso "6/6 Captura en vivo (phyphox)"
    Start-Process $dat -ArgumentList @("-m", "herramientas.captura_phyphox_remoto", "--url", $Phyphox)
    Start-Sleep -Seconds 3
    Start-Process "http://127.0.0.1:8090/"
    Write-Host "Etiquetas con H R G T O I P en la ventana de la captura (o con los botones de la vista en vivo)."
}
Paso "Listo. Base: $base · tablero http://localhost:8081/tablero · mapa http://localhost:8080"
