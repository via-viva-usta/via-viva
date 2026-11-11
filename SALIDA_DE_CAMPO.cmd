@echo off
rem Doble clic para la salida de campo: 1) doctor  2) si está LISTO, captura con phyphox + tablero (localhost:8000).
rem Pasos completos en README_SALIDA.md.
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title VÍA VIVA - salida de campo
echo.
echo  == 1/2  Pre-chequeo (doctor) ==
call viaviva.cmd doctor
if errorlevel 1 (
  echo.
  echo  Hay algo en FALTA. Corrija y vuelva a abrir este archivo.
  echo  Si quiere capturar igual, escriba S y Enter; cualquier otra tecla cierra.
  set /p SEGUIR=^>
  if /i not "!SEGUIR!"=="S" exit /b 1
)
echo.
echo  == 2/2  Captura (Q o Ctrl+C para terminar; el RESUMEN sale al final) ==
call viaviva.cmd capture --abrir
echo.
pause
