"""La bitácora de «fin» cuenta solo la sesión (antes sumaba desde que arrancó la fuente: 525 004 muestras en una sesión
de 180 629) y el dataset avisa si hay sesiones grabadas desde una reproducción."""
import json

from viaviva import sesiones
from viaviva.nucleo import Nucleo


def _fin(carpeta):
    lineas = (carpeta / "bitacora.jsonl").read_text(encoding="utf-8").splitlines()
    return json.loads(lineas[-1])


def test_fin_cuenta_solo_la_sesion(tmp_path):
    n = Nucleo(100.0, dir_grabaciones=tmp_path)
    n.acc([(i / 100, 0.0, 0.0, 9.81) for i in range(500)])          # antes de grabar
    n.conexion(False)
    n.conexion(True)                                                # una reconexión antes de grabar
    n.iniciar_grabacion("a")
    n.acc([(5 + i / 100, 0.0, 0.0, 9.81) for i in range(300)])
    fin = _fin(tmp_path / n.detener_grabacion())
    assert fin["muestras"] == 300 and fin["reconexiones"] == 0


def test_sesion_de_reproduccion_se_reconoce(tmp_path):
    real, prueba = tmp_path / "sesion_2026-11-18_0619", tmp_path / "sesion_2026-11-12_1645"
    for c, origen in ((real, "nodo"), (prueba, "simulado")):
        c.mkdir()
        (c / "bitacora.jsonl").write_text(json.dumps({"tipo": "inicio", "origen": origen}) + "\n", encoding="utf-8")
    assert not sesiones._es_de_prueba(real) and sesiones._es_de_prueba(prueba)
    assert sesiones._es_de_prueba(tmp_path / "sesion_x_SINTETICO")
