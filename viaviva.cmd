@echo off
rem VÍA VIVA: "viaviva doctor", "viaviva capture", "viaviva capture --replay <export.zip>", "viaviva serve", ...
rem Usa viaviva\.venv (lo crea viaviva\instalar_pc.ps1); si no existe, el venv de dataset.
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set "RAIZ=%~dp0"
set "PY=%RAIZ%viaviva\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=%RAIZ%dataset\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo No hay entorno de Python. Ejecute primero:  powershell -ExecutionPolicy Bypass -File viaviva\instalar_pc.ps1
  exit /b 2
)
pushd "%RAIZ%"
"%PY%" -m viaviva %*
set CODIGO=%ERRORLEVEL%
popd
exit /b %CODIGO%
