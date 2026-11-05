# VÍA VIVA — demo en un comando (PowerShell, desde cualquier carpeta).
#
#   .\demo\iniciar.ps1            usa la base real; si no tiene eventos ni reportes, cambia sola a la base DEMO
#   .\demo\iniciar.ps1 -Demo      fuerza la base DEMO (data\via_viva_demo.db, datos marcados DEMO)
#   .\demo\iniciar.ps1 -SinBot -SinCelular
#
# Levanta en orden: (1) base, (2) tablero Java, (3) mapa web, (4) bot de Telegram, (5) página del clasificador para el
# celular. Cada servicio abre su propia ventana; se cierran con Ctrl+C en cada una. Guion: docs\demo.md.
param([switch]$Demo, [switch]$SinBot, [switch]$SinCelular, [switch]$SinTablero)
$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz
$env:PYTHONIOENCODING = "utf-8"
$etl = Join-Path $raiz "etl\.venv\Scripts\python.exe"
$bot = Join-Path $raiz "bot\.venv\Scripts\python.exe"
function Paso($t) { Write-Host "`n== $t" -ForegroundColor Yellow }

# 1. Base: real o DEMO
Paso "1/5 Base de datos"
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
    Paso "2/5 Tablero Java"
    $jar = Join-Path $raiz "dashboard-java\dist\TableroViaViva.jar"
    if (-not (Test-Path $jar)) {
        $ant = "C:\Program Files\NetBeans-25\netbeans\extide\ant\bin\ant.bat"
        $copy = "C:\Program Files\NetBeans-25\netbeans\java\ant\extra\org-netbeans-modules-java-j2seproject-copylibstask.jar"
        & $ant -q -f dashboard-java\build.xml "-Dlibs.CopyLibs.classpath=$copy" jar
    }
    Start-Process java -ArgumentList "-jar", "`"$jar`"", "`"$base`""
}

# 3. Mapa web (estático): se sirve en http://localhost:8080 para que cargue datos.js
Paso "3/5 Mapa web"
& $etl web\exportar.py
Start-Process $etl -ArgumentList "-m", "http.server", "8080", "--directory", "web"
Start-Sleep -Seconds 2
Start-Process "http://localhost:8080/"

# 4. Bot de Telegram (necesita TELEGRAM_BOT_TOKEN en .env; nunca se muestra)
if (-not $SinBot) {
    Paso "4/5 Bot de Telegram"
    if (Select-String -Path (Join-Path $raiz ".env") -Pattern "^TELEGRAM_BOT_TOKEN=.+" -Quiet) {
        Start-Process $bot -ArgumentList "bot\bot.py"
        Write-Host "Bot corriendo en otra ventana (sugiere la clase con la CNN si hay modelo)."
    } else { Write-Host "Falta TELEGRAM_BOT_TOKEN en .env: el bot no arranca." -ForegroundColor Red }
}

# 5. Clasificador en el celular (TFLite en el navegador, mismo WiFi)
if (-not $SinCelular) {
    Paso "5/5 Clasificador para el celular"
    if (Test-Path (Join-Path $raiz "dataset\salidas\ultimo.txt")) {
        Start-Process $etl -ArgumentList "web\clasificador\preparar.py", "--servir"
        Write-Host "Ver la URL en la ventana nueva y abrirla en el iPhone (mismo WiFi)."
    } else { Write-Host "No hay modelo de fotos (dataset\salidas): entrenar con dataset.modelo." -ForegroundColor Red }
}
Paso "Listo. Base: $base"
