# VÍA VIVA — programa el scraping diario (R5) en el Programador de tareas de Windows (schtasks), para el usuario actual.
#
#   .\herramientas\programar_scraping.ps1              crea o actualiza la tarea "VIA VIVA scraping diario" (06:30)
#   .\herramientas\programar_scraping.ps1 -Hora 21:00
#   .\herramientas\programar_scraping.ps1 -Quitar      borra la tarea
#
# La tarea corre etl\scraping\diario.cmd (IDEAM incremental + noticias + chequeo de frescura) y deja el log en
# data\logs\scraping_diario.jsonl. Ver las corridas: etl\.venv\Scripts\python -m etl.scraping.diario --resumen
# Solo corre si el PC está encendido y la sesión abierta a esa hora (tarea de usuario, sin guardar contraseña).
param([string]$Hora = "06:30", [switch]$Quitar)
$nombre = "VIA VIVA scraping diario"
if ($Quitar) { schtasks /Delete /TN $nombre /F; exit $LASTEXITCODE }
$cmd = Join-Path (Split-Path -Parent $PSScriptRoot) "etl\scraping\diario.cmd"
if (-not (Test-Path $cmd)) { throw "No existe $cmd" }
schtasks /Create /TN $nombre /TR "`"$cmd`"" /SC DAILY /ST $Hora /F
if ($LASTEXITCODE -eq 0) {
    Write-Host "Tarea '$nombre' programada a las $Hora. Probarla ya: schtasks /Run /TN `"$nombre`""
}
