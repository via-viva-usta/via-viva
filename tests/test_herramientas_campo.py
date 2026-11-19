"""auditar_sesion y comparar_detectores con datos SINTÉTICOS: solo comprueban que el flujo corre y detecta problemas
conocidos (hora desfasada); no son evidencia de precisión."""
import json
import time

from herramientas import auditar_sesion, comparar_detectores
from tests.test_viaviva import _export_sintetico
from viaviva.nucleo import Nucleo


def _sesion(tmp_path):
    n = Nucleo(100.0, dir_grabaciones=tmp_path)
    n.acc([(i / 100, 0.0, 0.0, 9.81) for i in range(300)])
    n.base_epoch = time.time() - 3.0          # los datos llegan más rápido que el reloj: t = 3 s es «ahora»
    n.iniciar_grabacion("prueba")
    for k in range(20):
        n.gps(3 + k, 5.53, -73.36, vel_ms=5.0)
        n.acc([(3 + k + i / 100, 0.0, 0.0, 9.81 + (3.0 if (k == 10 and i == 50) else 0.0)) for i in range(100)])
    n.etiquetar("hueco", origen="prueba")
    return tmp_path / n.detener_grabacion()


def test_auditar_sesion_ok_y_hora_desfasada(tmp_path):
    c = _sesion(tmp_path)
    inf = auditar_sesion.auditar(c)
    textos = [q for _, q, _ in inf.items]
    assert any(q.startswith("Hora de la sesión = reloj") for q in textos), inf.texto()
    assert inf.datos["marcas"]["vigentes"] == 1 and inf.datos["sensores"]["Accelerometer.csv"]["huecos"] == 0
    # el caso del 18-nov: meta/time.csv con +2 109 s
    meta = c / "meta" / "time.csv"
    lineas = meta.read_text(encoding="utf-8").splitlines()
    campos = lineas[1].split(",")
    campos[2] = f"{float(campos[2]) + 2109:.6f}"
    meta.write_text(lineas[0] + "\n" + ",".join(campos) + "\n", encoding="utf-8")
    inf = auditar_sesion.auditar(c)
    assert inf.fallas >= 1 and any("desfasada +2109" in q for _, q, _ in inf.items)
    assert auditar_sesion.main([str(c), "--json", str(tmp_path / "a.json")]) == 1
    assert json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))["datos"]["hora_fuente_menos_pc_s"] > 2000


def test_comparar_detectores_mismas_marcas_y_html(tmp_path):
    exp = _export_sintetico(tmp_path / "export", segundos=40)
    (tmp_path / "export_etiquetas.csv").write_text("t_s,clase\n10,hueco\n20,hueco\n30,resalto\n", encoding="utf-8")
    r = comparar_detectores.comparar(exp)
    assert r["marcas"] == 3 and r["en_vivo"]["eventos"] >= 1 and r["analisis"]["eventos"] >= 0
    assert set(r["en_vivo"]) >= {"tp", "fp", "fn", "por_clase"} and r["tolerancia_s"] > 0
    pagina = comparar_detectores.html_informe([r])
    assert pagina.startswith("<!doctype html>") and "<svg" in pagina and "5.53" not in pagina   # sin coordenadas
    assert comparar_detectores.comparar(exp, "adxl2")["error"].startswith("Accelerometer_adxl2.csv")
