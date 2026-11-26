"""config/simulacion.yaml + viaviva/modelo_estado.py + GET /api/modelo: un solo lugar para los umbrales de simulación y
las cifras de inferencia, siempre rotuladas SIMULADO, y listo para recibir el estado del API sin rehacer la interfaz."""
import dataclasses
import json

import yaml

from tests.test_viaviva import _base_con_calle, _cliente
from viaviva import config, modelo_estado


def _sim():
    return yaml.safe_load(modelo_estado.RUTA_SIMULACION.read_text(encoding="utf-8"))


def test_umbrales_de_simulacion_coinciden_con_el_codigo():
    """El YAML no cambia umbrales: repite los vigentes. Si se calibra, hay que cambiar ambos lados."""
    u = _sim()["umbrales"]
    assert u["detector_en_vivo"] == dataclasses.asdict(config.ParametrosUmbral())
    det = yaml.safe_load((config.RAIZ / "config" / "detector.yaml").read_text(encoding="utf-8"))
    for clave, valor in u["detector_analisis"].items():
        assert det[clave] == valor, clave
    from viaviva import ventanas
    assert u["ventanas_modelo"] == {"ventana_s": ventanas.VENTANA_S, "paso_s": ventanas.PASO_S,
                                    "tolerancia_s": ventanas.TOLERANCIA_S}


def test_la_simulacion_siempre_va_rotulada():
    e = modelo_estado.cargar(ruta_api=config.RAIZ / "no-existe.json")
    assert e["fuente"] == "simulacion" and e["simulado"] is True and e["rotulo"] == "SIMULADO"
    assert e["modelos"] and all("metricas_simuladas" in m for m in e["modelos"])
    assert "PC" in e["cifras_inferencia"]["medidas_en"] and e["cifras_inferencia"]["etapas"]


def test_prefiere_el_json_del_api_y_no_lo_muestra_como_real_si_no_lo_dice(tmp_path):
    api = tmp_path / "estado_api.json"
    api.write_text(json.dumps({"modelos": [{"id": "m-api"}], "cifras_inferencia": {"etapas": []}}), encoding="utf-8")
    e = modelo_estado.cargar(ruta_api=api)
    assert e["fuente"] == "api" and e["modelos"][0]["id"] == "m-api"
    assert e["simulado"] is True and e["rotulo"] == "SIMULADO"          # sin "simulado": false explícito, sigue rotulado
    api.write_text(json.dumps({"simulado": False, "rotulo": "Pi, 2026-12", "modelos": []}), encoding="utf-8")
    e = modelo_estado.cargar(ruta_api=api)
    assert e["simulado"] is False and e["rotulo"] == "Pi, 2026-12"


def test_un_json_del_api_roto_vuelve_a_la_simulacion_con_aviso(tmp_path):
    api = tmp_path / "estado_api.json"
    api.write_text("{no es json", encoding="utf-8")
    e = modelo_estado.cargar(ruta_api=api)
    assert e["fuente"] == "simulacion" and e["rotulo"] == "SIMULADO" and "no se pudo leer" in e["aviso"]


def test_api_modelo_para_quien_puede_leer_el_tablero(tmp_path):
    ctx, c = _cliente(tmp_path, _base_con_calle(tmp_path), segundos=5, velocidad=5)
    try:
        r = c.get("/api/modelo")                     # sin usuarios creados, 127.0.0.1 entra como editor
        assert r.status_code == 200
        d = r.json()
        assert d["rotulo"] == "SIMULADO" and d["umbrales"]["detector_en_vivo"]["p2p_min_g"] == 0.30
        html = c.get("/tablero").text
        assert 'data-p="p-modelo"' in html and "/api/modelo" in html
    finally:
        ctx.fuente.cerrar()
