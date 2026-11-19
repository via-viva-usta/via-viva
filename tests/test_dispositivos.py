"""Rol y alias de cada equipo, fuente identificada y estado periódico de la fuente en la bitácora (traspaso 19-nov).
La fuente del cliente de prueba es una reproducción SINTÉTICA: solo se prueba la mecánica."""
import json

from tests.test_viaviva import _base_con_calle, _cliente
from viaviva.app import agente_de
from viaviva.nucleo import Nucleo


def _bit(carpeta):
    return [json.loads(x) for x in (carpeta / "bitacora.jsonl").read_text(encoding="utf-8").splitlines()]


def test_registro_de_dispositivos_y_estado_de_fuente(tmp_path):
    n = Nucleo(100.0, dir_grabaciones=tmp_path)
    assert n.registrar_dispositivo("camara", "phone-cam-1", "iOS · Safari") == {
        "rol": "camara", "alias": "PHONE-CAM-1", "sesion": None}
    for rol, alias in (("piloto", "PHONE-A"), ("marcador", "Juan Pérez"), ("marcador", "")):
        try:
            n.registrar_dispositivo(rol, alias)
            raise AssertionError("debía rechazarse")
        except ValueError:
            pass
    n.iniciar_grabacion("roles")
    r = n.registrar_dispositivo("marcador", "PHONE-A", "Android · Firefox")
    assert r["sesion"] and n.registrar_dispositivo("marcador", "PHONE-A")["sesion"] == r["sesion"]
    n._ult_estado_fuente -= 61                                     # pasó el minuto: se escribe el estado
    n.acc([(i / 100, 0.0, 0.0, 9.81) for i in range(100)])
    bit = _bit(tmp_path / n.detener_grabacion())
    inicio = bit[0]
    assert inicio["fuente"]["alias"] == "desconocido" and {"so", "arquitectura"} <= set(inicio["equipo"])
    disp = [(b["accion"], b["alias"], b["rol"]) for b in bit if b["tipo"] == "dispositivo"]
    assert disp == [("presente al iniciar", "PHONE-CAM-1", "camara"), ("conectado", "PHONE-A", "marcador")]
    est = next(b for b in bit if b["tipo"] == "estado_fuente")
    assert est["fs_efectiva_hz"] > 0 and "hora_fuente_menos_pc_s" in est and est["conectado"] in (True, False)
    assert {d["alias"] for d in n.lista_dispositivos()} == {"PHONE-CAM-1", "PHONE-A"}


def test_agente_corto_sin_version():
    ua = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
          "FxiOS/133.0 Mobile/15E148 Safari/605.1.15")
    assert agente_de(ua) == "iOS · Firefox"
    assert agente_de("") == "desconocido · desconocido"


def test_api_dispositivo_confirma_rol_y_sesion(tmp_path, monkeypatch):
    monkeypatch.setenv("VIAVIVA_ALIAS_FUENTE", "rep-1")
    ctx, c = _cliente(tmp_path, _base_con_calle(tmp_path), segundos=5, velocidad=5)
    try:
        r = c.post("/api/dispositivo", json={"rol": "camara", "alias": "cam-1"}).json()
        assert r["ok"] and r["alias"] == "CAM-1" and r["sesion"] is None
        assert c.post("/api/dispositivo", json={"rol": "x", "alias": "CAM-1"}).status_code == 400
        lista = c.get("/api/dispositivos").json()
        assert lista["fuente"] == {"rol": "reproduccion", "alias": "REP-1", "fuente": "replay"}
        assert lista["dispositivos"][0]["alias"] == "CAM-1"
    finally:
        ctx.fuente.cerrar()
