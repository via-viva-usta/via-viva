from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from viaviva import actualizacion


def git(carpeta: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(carpeta), *args], capture_output=True, text=True)
    if r.returncode:
        raise AssertionError(f"git {args!r} falló: {r.stderr}")
    return r.stdout.strip()


def repositorio_limpio(tmp_path: Path) -> tuple[Path, Path, Path]:
    trabajo = tmp_path / "trabajo"
    trabajo.mkdir()
    git(trabajo, "init", "--initial-branch=main")
    git(trabajo, "config", "user.name", "Vía Viva tests")
    git(trabajo, "config", "user.email", "tests@example.invalid")
    (trabajo / "README.md").write_text("versión inicial\n", encoding="utf-8")
    git(trabajo, "add", "README.md")
    git(trabajo, "commit", "-m", "inicial")

    origen = trabajo / ".git"
    instalacion = tmp_path / "clon-limpio"
    shutil.copytree(trabajo, instalacion, ignore=shutil.ignore_patterns(".git"))
    shutil.copytree(trabajo / ".git", instalacion / ".git")
    git(instalacion, "remote", "add", "origin", str(origen))
    git(instalacion, "update-ref", "refs/remotes/origin/main", git(instalacion, "rev-parse", "HEAD"))
    git(instalacion, "branch", "--set-upstream-to=origin/main", "main")
    return trabajo, origen, instalacion


def publicar_cambio(trabajo: Path, *, dependencias: bool = False) -> str:
    if dependencias:
        requisitos = trabajo / "viaviva" / "requirements-pc.txt"
        requisitos.parent.mkdir(exist_ok=True)
        requisitos.write_text("# lista de prueba\n", encoding="utf-8")
        git(trabajo, "add", "viaviva/requirements-pc.txt")
    else:
        (trabajo / "README.md").write_text("versión nueva\n", encoding="utf-8")
        git(trabajo, "add", "README.md")
    git(trabajo, "commit", "-m", "actualización")
    return git(trabajo, "rev-parse", "HEAD")


def simular_fetch(monkeypatch, origen: Path) -> None:
    git_real = actualizacion._git

    def fetch_local(raiz: Path, *args: str, **kwargs) -> str:
        if args and args[0] == "fetch":
            objetos = Path(raiz) / ".git" / "objects"
            for archivo in (origen / "objects").rglob("*"):
                relativo = archivo.relative_to(origen / "objects")
                destino = objetos / relativo
                if archivo.is_dir():
                    destino.mkdir(exist_ok=True)
                elif not destino.exists():
                    shutil.copyfile(archivo, destino)
            nuevo = subprocess.run(["git", "--git-dir", str(origen), "rev-parse", "refs/heads/main"],
                                   check=True, capture_output=True, text=True).stdout.strip()
            git_real(raiz, "update-ref", "refs/remotes/origin/main", nuevo)
            return ""
        return git_real(raiz, *args, **kwargs)

    monkeypatch.setattr(actualizacion, "_git", fetch_local)


def test_aplica_fast_forward_instala_dependencias_y_revierte(tmp_path: Path, monkeypatch) -> None:
    trabajo, origen, instalacion = repositorio_limpio(tmp_path)
    anterior = git(instalacion, "rev-parse", "HEAD")
    nuevo = publicar_cambio(trabajo, dependencias=True)
    simular_fetch(monkeypatch, origen)
    instalaciones: list[Path] = []

    estado = actualizacion.estado(instalacion, origen_esperado=str(origen))
    assert estado["estado"] == "disponible", estado
    assert estado["dependencias"] is True

    aplicada = actualizacion.aplicar(instalacion, origen_esperado=str(origen), instalador=instalaciones.append)
    assert aplicada["ok"] is True
    assert git(instalacion, "rev-parse", "HEAD") == nuevo
    assert len(instalaciones) == 1

    reversa = actualizacion.revertir(instalacion, origen_esperado=str(origen), instalador=instalaciones.append)
    assert reversa["ok"] is True
    assert git(instalacion, "rev-parse", "HEAD") == anterior
    assert len(instalaciones) == 2


def test_sin_internet_conserva_version_instalada(tmp_path: Path, monkeypatch) -> None:
    trabajo, origen, instalacion = repositorio_limpio(tmp_path)
    publicar_cambio(trabajo)
    anterior = git(instalacion, "rev-parse", "HEAD")
    git_real = actualizacion._git

    def sin_red(raiz: Path, *args: str, **kwargs) -> str:
        if args and args[0] == "fetch":
            raise actualizacion.ErrorActualizacion("simulación de desconexión")
        return git_real(raiz, *args, **kwargs)

    monkeypatch.setattr(actualizacion, "_git", sin_red)
    resultado = actualizacion.estado(instalacion, origen_esperado=str(origen))
    assert resultado["estado"] == "sin_internet"
    assert git(instalacion, "rev-parse", "HEAD") == anterior
    assert git(instalacion, "status", "--porcelain") == ""


def test_no_actualiza_durante_grabacion_ni_con_arbol_sucio(tmp_path: Path) -> None:
    trabajo, origen, instalacion = repositorio_limpio(tmp_path)
    publicar_cambio(trabajo)
    en_grabacion = actualizacion.aplicar(instalacion, grabando=True, origen_esperado=str(origen))
    assert en_grabacion["estado"] == "grabando"

    (instalacion / "README.md").write_text("edición local\n", encoding="utf-8")
    sucio = actualizacion.aplicar(instalacion, origen_esperado=str(origen))
    assert sucio["estado"] == "bloqueado"
    assert "cambios locales" in sucio["mensaje"]


def test_rechaza_rama_distinta_y_remoto_no_oficial(tmp_path: Path) -> None:
    _, origen, instalacion = repositorio_limpio(tmp_path)
    git(instalacion, "switch", "-c", "prueba")
    fuera_de_main = actualizacion.estado(instalacion, origen_esperado=str(origen))
    assert fuera_de_main["estado"] == "bloqueado"
    assert "rama main" in fuera_de_main["mensaje"]

    git(instalacion, "switch", "main")
    git(instalacion, "remote", "set-url", "origin", "https://example.invalid/otro/repo.git")
    otro_origen = actualizacion.estado(instalacion)
    assert otro_origen["estado"] == "bloqueado"
    assert "repositorio oficial" in otro_origen["mensaje"]


def test_clon_de_campo_en_etiqueta_nunca_se_mueve(tmp_path: Path, monkeypatch) -> None:
    """Carril de campo: un clon puesto en una etiqueta (HEAD separado) no se actualiza ni se revierte, aunque main
    haya avanzado. Así la versión congelada para la prueba en el carro no cambia con el botón «Actualizar»."""
    trabajo, origen, instalacion = repositorio_limpio(tmp_path)
    git(instalacion, "tag", "campo-prueba")
    git(instalacion, "-c", "advice.detachedHead=false", "checkout", "campo-prueba")
    congelado = git(instalacion, "rev-parse", "HEAD")
    publicar_cambio(trabajo)
    simular_fetch(monkeypatch, origen)
    e = actualizacion.estado(instalacion, origen_esperado=str(origen))
    assert e["estado"] == "bloqueado" and not e["disponible"] and not e["revertible"]   # el botón queda oculto
    assert actualizacion.aplicar(instalacion, origen_esperado=str(origen))["estado"] == "bloqueado"
    assert actualizacion.revertir(instalacion, origen_esperado=str(origen))["estado"] == "bloqueado"
    assert git(instalacion, "rev-parse", "HEAD") == congelado and git(instalacion, "branch", "--show-current") == ""
