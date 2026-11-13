"""Actualizaciones locales seguras desde la rama main del repo oficial.

Solo avanza un clon limpio y sin divergencias. Nunca modifica los datos de campo,
`.env` ni archivos ignorados; el respaldo de reversa vive dentro de `.git`.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

ORIGEN = "https://github.com/via-viva-usta/via-viva.git"
_HASH = re.compile(r"^[0-9a-f]{40}$")
_DEPENDENCIAS = {"viaviva/requirements-pc.txt"}


class ErrorActualizacion(RuntimeError):
    """El clon no cumple las condiciones de actualización."""


def _git(raiz: Path, *args: str, timeout: float = 20) -> str:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    try:
        r = subprocess.run(["git", "-C", str(raiz), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, env=env, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ErrorActualizacion("Git no está disponible o la conexión tardó demasiado.") from e
    if r.returncode:
        raise ErrorActualizacion("Git no pudo completar la operación de actualización.")
    return r.stdout.strip()


def _remoto_permitido(observado: str, esperado: str) -> bool:
    if esperado != ORIGEN:
        # Solo para pruebas con un remoto Git local; producción siempre usa ORIGEN.
        try:
            return Path(observado).resolve() == Path(esperado).resolve()
        except (OSError, ValueError):
            return False
    if observado.startswith("git@github.com:"):
        ruta = observado.removeprefix("git@github.com:")
    else:
        u = urlsplit(observado)
        if u.scheme != "https" or u.hostname != "github.com" or u.username or u.password:
            return False
        ruta = u.path.lstrip("/")
    return ruta.rstrip("/").removesuffix(".git").lower() == "via-viva-usta/via-viva"


def _limpio(raiz: Path) -> bool:
    return not _git(raiz, "status", "--porcelain=v1", "--untracked-files=all")


def _git_dir(raiz: Path) -> Path:
    p = Path(_git(raiz, "rev-parse", "--git-path", "vv-rollback.json"))
    return p if p.is_absolute() else raiz / p


def _marcador_valido(raiz: Path, actual: str | None = None) -> dict | None:
    try:
        d = json.loads(_git_dir(raiz).read_text(encoding="utf-8"))
        if not _HASH.fullmatch(d.get("antes", "")) or not _HASH.fullmatch(d.get("despues", "")):
            return None
        if actual is not None and actual != d["despues"]:
            return None
        return d
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _archivos_dependencias(raiz: Path, antes: str, despues: str) -> list[str]:
    lista = _git(raiz, "diff", "--name-only", antes, despues).splitlines()
    return [p for p in lista if p.lower() in _DEPENDENCIAS]


def _archivo_requisitos(raiz: Path) -> Path:
    return raiz / "viaviva" / "requirements-pc.txt"


def _instalar_dependencias(raiz: Path) -> None:
    requisitos = _archivo_requisitos(raiz)
    if not requisitos.is_file():
        raise ErrorActualizacion("La nueva versión no contiene el archivo de dependencias esperado.")
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requisitos)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
                           env={**os.environ, "PIP_DISABLE_PIP_VERSION_CHECK": "1"}, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ErrorActualizacion("No se pudo ejecutar pip para instalar las dependencias.") from e
    if r.returncode:
        raise ErrorActualizacion("No se pudieron instalar las dependencias. Se intentará volver a la versión anterior.")


def _base(raiz: Path, origen_esperado: str) -> tuple[Path, str, str]:
    raiz = Path(raiz).resolve()
    tope = Path(_git(raiz, "rev-parse", "--show-toplevel")).resolve()
    if tope != raiz:
        raise ErrorActualizacion("La app debe ejecutarse desde la carpeta raíz del clon.")
    if _git(raiz, "branch", "--show-current") != "main":
        raise ErrorActualizacion("Las actualizaciones automáticas están habilitadas solo en la rama main.")
    remoto = _git(raiz, "remote", "get-url", "origin")
    if not _remoto_permitido(remoto, origen_esperado):
        raise ErrorActualizacion("El remoto origin no es el repositorio oficial de VÍA VIVA.")
    if not _limpio(raiz):
        raise ErrorActualizacion("Hay cambios locales pendientes. Se conservan y no se actualiza.")
    for nombre in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "rebase-apply", "rebase-merge"):
        if (_git_dir(raiz).parent / nombre).exists():
            raise ErrorActualizacion("Hay una operación Git en curso; complétela antes de actualizar.")
    head = _git(raiz, "rev-parse", "HEAD")
    if not _HASH.fullmatch(head):
        raise ErrorActualizacion("No se pudo leer la versión instalada.")
    return raiz, head, remoto


def estado(raiz: Path, *, origen_esperado: str = ORIGEN, timeout: float = 8) -> dict:
    """Comprueba main en GitHub; sin red devuelve la versión instalada como utilizable."""
    try:
        raiz, head, _ = _base(raiz, origen_esperado)
    except ErrorActualizacion as e:
        return {"estado": "bloqueado", "mensaje": str(e), "actual": "", "disponible": False,
                "dependencias": False, "revertible": False}
    try:
        _git(raiz, "fetch", "--quiet", "--no-tags", "origin", "main:refs/remotes/origin/main", timeout=timeout)
    except ErrorActualizacion:
        return {"estado": "sin_internet", "mensaje": "Sin conexión con GitHub; se conserva esta versión.",
                "actual": head[:7], "disponible": False, "dependencias": False,
                "revertible": _marcador_valido(raiz, head) is not None}
    try:
        remoto = _git(raiz, "rev-parse", "refs/remotes/origin/main")
        if not _HASH.fullmatch(remoto):
            raise ErrorActualizacion("No se pudo identificar la versión publicada.")
        ancestro = subprocess.run(["git", "-C", str(raiz), "merge-base", "--is-ancestor", head, remoto],
                                  capture_output=True, timeout=timeout, check=False)
        if ancestro.returncode not in (0, 1):
            raise ErrorActualizacion("No se pudo comparar la versión instalada con main.")
        if ancestro.returncode == 1:
            return {"estado": "divergido", "mensaje": "La copia local no es un avance directo de main.",
                    "actual": head[:7], "disponible": False, "dependencias": False,
                    "revertible": _marcador_valido(raiz, head) is not None}
        disponible = head != remoto
        deps = _archivos_dependencias(raiz, head, remoto) if disponible else []
        return {"estado": "disponible" if disponible else "al_dia",
                "mensaje": "Hay una actualización lista." if disponible else "La app ya está al día.",
                "actual": head[:7], "nueva": remoto[:7], "disponible": disponible,
                "dependencias": bool(deps), "archivos_dependencias": deps,
                "revertible": _marcador_valido(raiz, head) is not None}
    except (ErrorActualizacion, subprocess.TimeoutExpired):
        return {"estado": "bloqueado", "mensaje": "No se pudo comparar el historial; no se cambió la app.",
                "actual": head[:7], "disponible": False, "dependencias": False,
                "revertible": _marcador_valido(raiz, head) is not None}


def aplicar(raiz: Path, *, grabando: bool = False, origen_esperado: str = ORIGEN,
            instalador=None) -> dict:
    """Avanza main sin tocar una sesión ni cambios locales; deja una reversa local."""
    if grabando:
        return {"ok": False, "estado": "grabando", "mensaje": "Termina y guarda la grabación antes de actualizar."}
    try:
        raiz, head, _ = _base(raiz, origen_esperado)
    except ErrorActualizacion as e:
        return {"ok": False, "estado": "bloqueado", "mensaje": str(e)}
    e = estado(raiz, origen_esperado=origen_esperado)
    if not e.get("disponible"):
        return {"ok": False, "estado": e["estado"], "mensaje": e["mensaje"], "actual": e.get("actual")}
    nuevo = _git(raiz, "rev-parse", "refs/remotes/origin/main")
    deps = _archivos_dependencias(raiz, head, nuevo)
    destino = _git_dir(raiz)
    temporal = None
    try:
        marcador_anterior = destino.read_bytes() if destino.exists() else None
        marcador = {"antes": head, "despues": nuevo, "dependencias": bool(deps),
                    "hora_utc": datetime.now(UTC).isoformat(timespec="seconds")}
        destino.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destino.parent, delete=False) as f:
            json.dump(marcador, f, ensure_ascii=False)
            temporal = Path(f.name)
        os.replace(temporal, destino)
    except OSError:
        if temporal is not None:
            try:
                temporal.unlink(missing_ok=True)
            except OSError:
                pass
        return {"ok": False, "estado": "bloqueado", "mensaje": "No se pudo preparar la reversa; no se cambió la app."}
    try:
        _git(raiz, "merge", "--ff-only", nuevo)
        if deps:
            (instalador or _instalar_dependencias)(raiz)
    except (ErrorActualizacion, OSError, subprocess.TimeoutExpired):
        reversa_codigo = False
        reversa_dependencias = not deps
        try:
            _git(raiz, "reset", "--hard", head)
            reversa_codigo = True
            if deps:
                (instalador or _instalar_dependencias)(raiz)
            reversa_dependencias = True
        except (ErrorActualizacion, OSError, subprocess.TimeoutExpired):
            pass
        try:
            if marcador_anterior is None:
                destino.unlink(missing_ok=True)
            else:
                destino.write_bytes(marcador_anterior)
        except OSError:
            pass
        if not reversa_codigo:
            return {"ok": False, "estado": "error_reversa",
                    "mensaje": "Falló la actualización y no se pudo restaurar el código. "
                               "Cierra la app y solicita revisión técnica.",
                    "dependencias": bool(deps), "reinstalar_manual": bool(deps)}
        return {"ok": False, "estado": "revertida",
                "mensaje": "Se restauró el código anterior." if reversa_dependencias else
                "Se restauró el código; revisa las dependencias con el instalador.",
                "dependencias": bool(deps), "reinstalar_manual": not reversa_dependencias}
    return {"ok": True, "estado": "actualizada", "mensaje": "Actualización instalada. Reiniciando VÍA VIVA.",
            "actual": head[:7], "nueva": nuevo[:7], "dependencias": bool(deps), "reiniciar": True}


def revertir(raiz: Path, *, grabando: bool = False, origen_esperado: str = ORIGEN,
             instalador=None) -> dict:
    """Vuelve al commit previo solo si la copia sigue limpia y en la versión recién actualizada."""
    if grabando:
        return {"ok": False, "estado": "grabando", "mensaje": "Termina y guarda la grabación antes de revertir."}
    try:
        raiz, head, _ = _base(raiz, origen_esperado)
    except ErrorActualizacion as e:
        return {"ok": False, "estado": "bloqueado", "mensaje": str(e)}
    d = _marcador_valido(raiz, head)
    if not d:
        return {"ok": False, "estado": "no_revertible", "mensaje": "No hay una actualización reciente que se pueda revertir."}
    try:
        _git(raiz, "reset", "--hard", d["antes"])
        if d.get("dependencias"):
            (instalador or _instalar_dependencias)(raiz)
    except (ErrorActualizacion, subprocess.TimeoutExpired):
        return {"ok": False, "estado": "revertida_con_error",
                "mensaje": "El código volvió a la versión anterior; revisa las dependencias con el instalador."}
    return {"ok": True, "estado": "revertida", "mensaje": "Se restauró la versión anterior. Reiniciando VÍA VIVA.",
            "actual": d["despues"][:7], "nueva": d["antes"][:7], "reiniciar": True}
