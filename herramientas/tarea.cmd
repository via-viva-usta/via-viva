@echo off
rem Empieza una tarea en una rama nueva SIEMPRE desde main al dia.  Uso:  herramientas\tarea.cmd dani/iconos-mapa
rem Prefijos: ac/ (app, motor, firmware), dani/ (web), compartida/ (los dos, avisando antes). Ver GUIA_TRABAJO.md.
setlocal
set "RAMA=%~1"
if "%RAMA%"=="" (
  echo Uso: herramientas\tarea.cmd ac/descripcion-corta   ^(o dani/... o compartida/...^)
  exit /b 2
)
echo %RAMA%| findstr /r /c:"^ac/[a-z0-9-][a-z0-9-]*$" /c:"^dani/[a-z0-9-][a-z0-9-]*$" /c:"^compartida/[a-z0-9-][a-z0-9-]*$" >nul
if errorlevel 1 (
  echo Nombre invalido: use ac/, dani/ o compartida/ y luego minusculas, numeros y guiones. Ej: dani/iconos-mapa
  exit /b 2
)
cd /d "%~dp0.."
for /f %%c in ('git status --porcelain') do (
  echo Hay cambios sin guardar. Haga commit o descartelos antes de empezar otra tarea.
  exit /b 1
)
git switch main || exit /b 1
git pull --ff-only origin main || exit /b 1
git switch -c %RAMA% || exit /b 1
echo.
echo Lista: rama %RAMA% creada desde main al dia. Al terminar: git push -u origin HEAD  y  gh pr create --fill
