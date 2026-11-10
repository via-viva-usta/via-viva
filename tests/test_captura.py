"""Fase A de punta a punta, sin iPhone: simulador de phyphox por HTTP → captura → sesión → RESUMEN, más el doctor."""
import csv
import json
import sqlite3
import time

from tests.test_viaviva import _base_con_calle, _export_sintetico
from viaviva import config


def _esperar(cond, segundos=15.0):
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_captura_por_http_con_corte_no_pierde_muestras(tmp_path):
    from viaviva.app import construir
    url = _base_con_calle(tmp_path)
    exp = _export_sintetico(tmp_path / "export", segundos=30)
    ctx = construir("replay-http", str(exp), velocidad=10, url_db=url, dir_grabaciones=tmp_path / "ses", sync=False)
    n, sim = ctx.n, ctx.simulador
    try:
        n.iniciar_grabacion("http")
        assert _esperar(lambda: n.n_acc > 500)
        sim.pausado = True                                     # se cae el hotspot
        assert _esperar(lambda: not n.conectado, 10)
        time.sleep(0.6)
        sim.pausado = False                                    # vuelve: phyphox guardó lo del corte
        assert _esperar(lambda: n.conectado, 10)
        e = n.etiquetar("hueco", origen="prueba")
        assert e["retardo_s"] == config.RETARDO_REACCION_S
        n.etiquetar("resalto", origen="prueba")
        assert n.deshacer()["clase"] == "resalto"
        n.destello(nota="inicio")
        assert _esperar(lambda: n.n_acc >= 3000, 20)           # toda la grabación (30 s a 100 Hz)
        assert n.n_eventos_total == 3 and n.reconexiones == 1
        carpeta = tmp_path / "ses" / n.detener_grabacion()
    finally:
        ctx.fuente.cerrar()
        sim.cerrar()
    with open(carpeta / "Accelerometer.csv", encoding="utf-8") as f:
        filas = list(csv.reader(f))
    assert filas[0] == ["Time (s)", "X (m/s^2)", "Y (m/s^2)", "Z (m/s^2)", "UTC PC (s)"]
    assert len(filas) - 1 == 3000                              # ni una muestra perdida pese al corte
    assert abs(float(filas[-1][4]) - time.time()) < 120        # UTC del PC en cada muestra
    bit = [json.loads(x) for x in (carpeta / "bitacora.jsonl").read_text(encoding="utf-8").splitlines()]
    tipos = [b["tipo"] for b in bit]
    assert tipos[0] == "inicio" and tipos[-1] == "fin" and "corte" in tipos and "reconexion" in tipos
    assert "deshacer" in tipos and "destello" in tipos
    vigentes = (tmp_path / "ses" / f"{carpeta.name}_etiquetas.csv").read_text(encoding="utf-8").splitlines()
    assert vigentes[0] == "t_s,clase" and [x.split(",")[1] for x in vigentes[1:]] == ["hueco"]
    db = sqlite3.connect(carpeta / "sesion.sqlite")
    assert db.execute("SELECT clase, anulada FROM etiquetas ORDER BY id").fetchall() == [("hueco", 0), ("resalto", 1)]
    assert db.execute("SELECT COUNT(*) FROM destellos").fetchone()[0] == 1
    db.close()
    r = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
    assert r["muestras"] == 3000 and r["cortes"] == 0 and r["marcas_por_clase"] == {"hueco": 1}
    assert r["deshechas"] == 1 and r["destellos"] == 1 and r["eventos_detectados"] == 3 and r["reconexiones"] == 1
    assert 0.12 < r["km"] < 0.16                              # 5 m/s × 29 s = 0,145 km
    texto = (carpeta / "RESUMEN.md").read_text(encoding="utf-8")
    assert "Falta el minuto quieto al INICIO" in texto and "Menos de 2 destellos" in texto


def test_doctor_listo_y_falta(tmp_path):
    from viaviva import doctor
    from viaviva.simulador_phyphox import SimuladorPhyphox
    sim = SimuladorPhyphox(_export_sintetico(tmp_path / "e", segundos=20), velocidad=1)
    try:
        time.sleep(1.0)
        inf = doctor.correr("phyphox", sim.url, puerto=0, dir_sesiones=tmp_path / "s", segundos=2, con_internet=False)
        estados = {q: e for e, q, _ in inf.filas}
        assert estados["Alcance a phyphox"] == "OK" and estados["Flujo 100 Hz"] == "OK" and estados["GPS"] == "OK"
    finally:
        sim.cerrar()
    inf = doctor.correr("phyphox", "http://127.0.0.1:9", puerto=0, dir_sesiones=tmp_path / "s", segundos=1,
                        con_internet=False)
    assert not inf.listo and "Alcance a phyphox" in inf.texto().splitlines()[-1]


def test_resumen_de_export_por_cli(tmp_path, capsys):
    from viaviva.cli import main
    exp = _export_sintetico(tmp_path / "export", segundos=20)
    assert main(["resumen", str(exp)]) == 0
    salida = capsys.readouterr().out
    assert "Muestras del acelerómetro" in salida and "2 000" in salida and (exp / "RESUMEN.md").exists()


def test_phyphox_autodetecta_y_mapea_buffers_reales(tmp_path):
    """El experimento puede llamar distinto a sus buffers: se leen de /config. Y la URL sin puerto se resuelve."""
    from viaviva import fuente_phyphox as fp
    from viaviva.simulador_phyphox import SimuladorPhyphox
    otros = {"acc": ("t_a", ["ax", "ay", "az"]), "giro": ("t_g", ["wx", "wy", "wz"]),
             "gps": ("t_p", ["la", "lo", "alt", "vel", "rumbo", "prec", "precz"])}
    sim = SimuladorPhyphox(_export_sintetico(tmp_path / "e", segundos=20), velocidad=5, grupos=otros)
    try:
        url, cfg = fp.descubrir(sim.url)
        assert url == sim.url and fp.mapear_buffers(cfg) == otros and fp.buffers_faltantes(cfg) == []
        cli = fp.ClientePhyphox(sim.url)
        assert cli.conectar() is not None and cli.grupos["gps"][1][0] == "la"
        time.sleep(0.5)
        filas = fp.filas_de(cli.nuevos({"acc": -1.0, "giro": -1.0, "gps": -1.0}), "acc", cli.grupos)
        assert len(filas) > 100 and len(filas[0]) == 4
    finally:
        sim.cerrar()
    assert fp.candidatos("http://172.20.10.1") == ["http://172.20.10.1", "http://172.20.10.1:8080"]
    assert fp.candidatos("172.20.10.1:8080") == ["http://172.20.10.1:8080", "http://172.20.10.1"]
    assert fp.descubrir("http://127.0.0.1:9", timeout=0.3)[0] is None
    sin_inputs = {"buffers": [{"name": n} for n in ("acc_time", "accX", "accY", "accZ", "gps_time", "gpsLat", "gpsLon")]}
    assert fp.mapear_buffers(sin_inputs) == fp.GRUPOS and fp.buffers_faltantes(sin_inputs) == []
    assert fp.buffers_faltantes({"buffers": [{"name": "acc_time"}]}) == ["accX", "accY", "accZ", "gpsLat", "gpsLon",
                                                                         "gps_time"]


def test_guardar_env_no_toca_lo_demas(tmp_path):
    from viaviva import config
    env = tmp_path / ".env"
    env.write_text("OTRA=1\nVIAVIVA_PHYPHOX_URL=http://viejo:8080\nULTIMA=x\n", encoding="utf-8")
    config.guardar_env("VIAVIVA_PHYPHOX_URL", "http://172.20.10.1", env)
    config.guardar_env("NUEVA", "2", env)
    assert env.read_text(encoding="utf-8").splitlines() == ["OTRA=1", "VIAVIVA_PHYPHOX_URL=http://172.20.10.1",
                                                            "ULTIMA=x", "NUEVA=2"]
