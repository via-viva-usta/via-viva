"""Regresión de dataset.externos.extraer_zip_seguro (revisión técnica del 7-nov): solo extrae dentro del destino."""
import stat
import zipfile

import pytest

from dataset.externos import extraer_zip_seguro


def _zip(ruta, miembros):
    with zipfile.ZipFile(ruta, "w") as z:
        for nombre, datos in miembros:
            if isinstance(datos, zipfile.ZipInfo):
                z.writestr(datos, "destino")
            else:
                z.writestr(nombre, datos)
    return ruta


def test_zip_valido(tmp_path):
    z = _zip(tmp_path / "ok.zip", [("images/a.png", b"x"), ("annotations/a.xml", b"<a/>"), ("leeme.txt", b"hola")])
    extraer_zip_seguro(z, tmp_path / "dest")
    assert (tmp_path / "dest" / "images" / "a.png").read_bytes() == b"x"
    assert (tmp_path / "dest" / "annotations" / "a.xml").exists()


def _enlace():
    info = zipfile.ZipInfo("enlace")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    return info


@pytest.mark.parametrize("nombre,datos", [("../escape.txt", b"x"), ("a/../../escape.txt", b"x"),
                                          ("..\\escape.txt", b"x"), ("/abs.txt", b"x"), ("C:/win.txt", b"x"),
                                          ("C:\\win.txt", b"x"), ("enlace", _enlace())])
def test_zip_malicioso_no_escribe_nada(tmp_path, nombre, datos):
    z = _zip(tmp_path / "malo.zip", [("bueno.txt", b"antes"), (nombre, datos)])
    destino = tmp_path / "dest"
    destino.mkdir()
    with pytest.raises(ValueError):
        extraer_zip_seguro(z, destino)
    assert not any(destino.iterdir())                    # se valida TODO antes de escribir el primer archivo
    assert not (tmp_path / "escape.txt").exists()


def test_zip_danado(tmp_path):
    malo = tmp_path / "danado.zip"
    malo.write_bytes(b"esto no es un zip")
    with pytest.raises(zipfile.BadZipFile):
        extraer_zip_seguro(malo, tmp_path / "dest")
