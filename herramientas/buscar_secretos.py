"""Busca tokens o secretos en TODO el historial de Git (git log -p --all). Nunca imprime el valor encontrado.

Uso (desde via-viva/): python -m herramientas.buscar_secretos
Sale con código 1 si encuentra algo. Revisa también que .env, secretos.h y kaggle.json nunca se hayan subido.
"""
from __future__ import annotations

import re
import subprocess
import sys

PATRONES = {
    "token de bot de Telegram": r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b",
    "token de GitHub": r"\bgh[pousr]_[A-Za-z0-9]{36,}\b",
    "clave de Google API": r"\bAIza[0-9A-Za-z_-]{35}\b",
    "clave de AWS": r"\bAKIA[0-9A-Z]{16}\b",
    "llave privada": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "clave de Kaggle": r'"key"\s*:\s*"[0-9a-f]{32}"',
    # (os.getenv / os.environ leen la variable del entorno: no son secretos)
    "variable de .env con valor": r"^\+\s*(TELEGRAM_BOT_TOKEN|BOT_SAL_HASH|SOCRATA_APP_TOKEN|KAGGLE_KEY)\s*=\s*(?!os\.)\S{8,}",
    "asignación de clave": r"(?i)^\+.*\b(password|contrase[ñn]a|secret|api_?key)\b\s*[=:]\s*['\"][^'\"\s]{8,}['\"]",
}
ARCHIVOS_PROHIBIDOS = [".env", "firmware/nodo-sensores/include/secretos.h", "kaggle.json"]


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    log = subprocess.run(["git", "log", "-p", "--all", "--no-color", "--format=COMMIT %h %ad", "--date=short"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    hallazgos, commit, archivo = [], "", ""
    for linea in log.splitlines():
        if linea.startswith("COMMIT "):
            commit = linea[7:]
            continue
        if linea.startswith("+++ b/"):
            archivo = linea[6:]
            continue
        if not linea.startswith("+") or linea.startswith("+++"):
            continue                                   # solo lo que se AGREGÓ en cada commit
        for nombre, patron in PATRONES.items():
            if re.search(patron, linea, flags=re.M):
                hallazgos.append((nombre, commit, archivo))
    subidos = []
    for a in ARCHIVOS_PROHIBIDOS:
        r = subprocess.run(["git", "log", "--all", "--format=%h", "--", a], capture_output=True, text=True).stdout.split()
        if r:
            subidos.append((a, r))
    n = len(log.split("\nCOMMIT ")) if log else 0
    print(f"Revisados {n} commits (todas las ramas), solo líneas agregadas.")
    for nombre, c, a in hallazgos:
        print(f"  POSIBLE SECRETO: {nombre} · commit {c} · {a}  (valor no mostrado)")
    for a, cs in subidos:
        print(f"  ARCHIVO PROHIBIDO EN EL HISTORIAL: {a} · commits {', '.join(cs)}")
    if not hallazgos and not subidos:
        print("Sin tokens ni secretos en el historial; .env, secretos.h y kaggle.json nunca se subieron.")
    sys.exit(1 if hallazgos or subidos else 0)


if __name__ == "__main__":
    main()
