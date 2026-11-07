# VÍA VIVA — todo en un comando (PowerShell, desde la carpeta via-viva).
#
#   .\iniciar.ps1                       base real (o DEMO si no tiene datos) + tablero + mapa + bot + clasificador
#   .\iniciar.ps1 -Demo                 fuerza la base DEMO (data\via_viva_demo.db, datos marcados DEMO)
#   .\iniciar.ps1 -Reproducir data\raw\phyphox\2026-11-07_03_pipe.zip   + captura en vivo REPRODUCIENDO una grabación
#   .\iniciar.ps1 -Phyphox http://172.20.10.1:8080                       + captura en vivo desde el iPhone (phyphox)
#   .\iniciar.ps1 -SinBot -SinCelular -SinTablero
#
# Levanta en orden: (1) base, (2) tablero Java, (3) mapa web, (4) bot de Telegram, (5) clasificador para el celular,
# (6) captura en vivo de phyphox (si se pide). Cada servicio abre su ventana; se cierran con Ctrl+C. Guion: docs\demo.md.
param([switch]$Demo, [switch]$SinBot, [switch]$SinCelular, [switch]$SinTablero, [string]$Reproducir = "",
      [string]$Phyphox = "")
$ErrorActionPreference = "Stop"
$raiz = $PSScriptRoot
Set-Location $raiz
$env:PYTHONIOENCODING = "utf-8"
$etl = Join-Path $raiz "etl\.venv\Scripts\python.exe"
$bot = Join-Path $raiz "bot\.venv\Scripts\python.exe"
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

# 2. Tablero Java (Estructuras de Datos)
if (-not $SinTablero) {
    Paso "2/6 Tablero Java"
    $jar = Join-Path $raiz "dashboard-java\dist\TableroViaViva.jar"
    if (-not (Test-Path $jar)) {
        $ant = "C:\Program Files\NetBeans-25\netbeans\extide\ant\bin\ant.bat"
        $copy = "C:\Program Files\NetBeans-25\netbeans\java\ant\extra\org-netbeans-modules-java-j2seproject-copylibstask.jar"
        & $ant -q -f dashboard-java\build.xml "-Dlibs.CopyLibs.classpath=$copy" jar
    }
    Start-Process java -ArgumentList "-jar", "`"$jar`"", "`"$base`""
}

# 3. Mapa web (estático): se sirve en http://localhost:8080 para que cargue datos.js
Paso "3/6 Mapa web"
& $etl web\exportar.py
Start-Process $etl -ArgumentList "-m", "http.server", "8080", "--directory", "web"
Start-Sleep -Seconds 2
Start-Process "http://localhost:8080/"

# 4. Bot de Telegram (necesita TELEGRAM_BOT_TOKEN en .env; nunca se muestra)
if (-not $SinBot) {
    Paso "4/6 Bot de Telegram"
    if (Select-String -Path (Join-Path $raiz ".env") -Pattern "^TELEGRAM_BOT_TOKEN=.+" -Quiet) {
        Start-Process $bot -ArgumentList "bot\bot.py"
        Write-Host "Bot corriendo en otra ventana (sugiere la clase con la CNN si hay modelo)."
    } else { Write-Host "Falta TELEGRAM_BOT_TOKEN en .env: el bot no arranca." -ForegroundColor Red }
}

# 5. Clasificador en el celular (TFLite en el navegador, mismo WiFi)
if (-not $SinCelular) {
    Paso "5/6 Clasificador para el celular"
    if (Test-Path (Join-Path $raiz "dataset\salidas\ultimo.txt")) {
        Start-Process $etl -ArgumentList "web\clasificador\preparar.py", "--servir"
        Write-Host "Ver la URL en la ventana nueva y abrirla en el iPhone (mismo WiFi)."
    } else { Write-Host "No hay modelo de fotos (dataset\salidas): entrenar con dataset.modelo." -ForegroundColor Red }
}
# 6. Captura en vivo de phyphox (iPhone por el acceso remoto) o reproducción de una grabación
if ($Reproducir -or $Phyphox) {
    Paso "6/6 Captura en vivo (phyphox)"
    $args6 = @("-m", "herramientas.captura_phyphox_remoto")
    if ($Reproducir) { $args6 += @("--reproducir", "`"$Reproducir`"") } else { $args6 += @("--url", $Phyphox) }
    Start-Process $dat -ArgumentList $args6
    Start-Sleep -Seconds 3
    Start-Process "http://127.0.0.1:8090/"
    Write-Host "Etiquetas con H R G T O I P en la ventana de la captura (o con los botones de la vista en vivo)."
}
Paso "Listo. Base: $base"
