"""Ingesta al dataset. Fixture SINTÉTICO mínimo, solo para la mecánica de archivos: nunca entra al dataset real ni a
métricas (la sesión se graba en tmp_path y se ingesta en tmp_path)."""
import json
import time

import pytest

from herramientas import ingestar_sesion as ing
from viaviva.nucleo import Nucleo


def _grabar(tmp_path, origen="nodo"):
    n = Nucleo(100.0, origen=origen, dir_grabaciones=tmp_path / "campo")
    n.acc([(i / 100, 0.0, 0.0, 9.81) for i in range(300)])
    n.base_epoch = time.time() - 3.0
    n.iniciar_grabacion("mecanica")
    for k in range(10):
        n.gps(3 + k, 5.53, -73.36, vel_ms=5.0)
        n.acc([(3 + k + i / 100, 0.0, 0.0, 9.81) for i in range(100)])
    n.etiquetar("hueco", origen="prueba")
    c = tmp_path / "campo" / n.detener_grabacion()
    (c / "video.mp4").write_bytes(b"0" * 100)                   # el video no se copia, solo se referencia
    return c


def test_ingesta_copia_verificada_y_motivos(tmp_path):
    c = _grabar(tmp_path)
    antes = {p.name: p.stat().st_mtime for p in c.iterdir()}
    p = ing.agregar(c, tmp_path / "ds")
    copia = tmp_path / "ds" / "sesiones" / c.name
    assert (copia / "Accelerometer.csv").read_bytes() == (c / "Accelerometer.csv").read_bytes()
    assert (tmp_path / "ds" / "sesiones" / f"{c.name}_etiquetas.csv").exists()
    assert not (copia / "video.mp4").exists() and p["videos_no_copiados"][0]["bytes"] == 100
    assert {x.name: x.stat().st_mtime for x in c.iterdir()} == antes          # el original no se tocó
    assert p["apto_entrenamiento"] is False and p["marcas_vigentes"] == 1 and p["marcas_revisadas"] == 0
    motivos = " ".join(p["motivos_no_apto"])
    assert "revisadas con video: 0 de 1" in motivos and "sin video" in motivos and "rol/alias" in motivos
    assert p["dispositivos"] == "desconocido"
    assert (tmp_path / "ds" / "meta" / c.name / "auditoria.json").exists()
    assert ing.main(["indice", "--destino", str(tmp_path / "ds")]) == 0
    assert "apto" in (tmp_path / "ds" / "indice.csv").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="ya está"):
        ing.agregar(c, tmp_path / "ds")


def test_rechaza_reproduccion_y_destino_en_el_repo(tmp_path):
    with pytest.raises(ValueError, match="reproducción o SINTÉTICA"):
        ing.agregar(_grabar(tmp_path / "a", origen="simulado"), tmp_path / "ds")
    with pytest.raises(ValueError, match="repositorio"):
        ing.agregar(_grabar(tmp_path / "b"), ing.REPO / "data" / "dataset_prueba")
    assert not (ing.REPO / "data" / "dataset_prueba").exists()


def test_hora_desfasada_queda_como_correccion_sin_aplicar(tmp_path):
    c = _grabar(tmp_path)
    meta = c / "meta" / "time.csv"
    enc, fila = meta.read_text(encoding="utf-8").splitlines()
    campos = fila.split(",")
    campos[2] = f"{float(campos[2]) + 2109:.6f}"
    meta.write_text(enc + "\n" + ",".join(campos) + "\n", encoding="utf-8")
    p = ing.agregar(c, tmp_path / "ds")
    corr = json.loads((tmp_path / "ds" / "meta" / c.name / "correcciones.json").read_text(encoding="utf-8"))
    assert 2105 < corr["restar_a_ts_utc_y_utc_s"] < 2113 and corr["aplicada"] is False
    assert any("desfasada" in m for m in p["motivos_no_apto"])
    # la copia conserva el meta/time.csv original (no se reescribe)
    assert (tmp_path / "ds" / "sesiones" / c.name / "meta" / "time.csv").read_text(encoding="utf-8") == meta.read_text(
        encoding="utf-8")
