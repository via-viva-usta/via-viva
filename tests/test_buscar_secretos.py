"""El buscador de secretos detecta un token FALSO en un repositorio temporal e ignora os.getenv."""
import subprocess

import pytest

from herramientas import buscar_secretos


def _repo(tmp_path, contenido):
    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.email", "prueba@ejemplo.org")
    git("config", "user.name", "prueba")
    (tmp_path / "config.py").write_text(contenido, encoding="utf-8")
    git("add", ".")
    git("commit", "-q", "-m", "prueba")


@pytest.mark.parametrize("contenido,esperado", [
    ('TOKEN = "123456789:' + "A" * 35 + '"\n', 1),                        # token de Telegram inventado
    ('TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")\n', 0),          # lee del entorno: no es secreto
])
def test_detecta_y_no_da_falsos_positivos(tmp_path, monkeypatch, capsys, contenido, esperado):
    _repo(tmp_path, contenido)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as fin:
        buscar_secretos.main()
    assert fin.value.code == esperado
    assert "123456789:AAAA" not in capsys.readouterr().out             # nunca imprime el valor
