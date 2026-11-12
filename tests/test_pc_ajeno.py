"""PC de otra persona: práctica sin datos de campo, arranque sin .env (PIN, Docker) y sesiones copiadas entre PCs."""
import asyncio
import csv
import shutil
import time

import httpx

from tests.test_viaviva import _base_con_calle, _cliente
from viaviva import config


def test_ejemplo_sintetico_se_crea_una_vez_y_se_reproduce(tmp_path, monkeypatch, capsys):
    from viaviva import ejemplo
    from viaviva.cli import main
    monkeypatch.setattr(ejemplo, "CARPETA", tmp_path / "SINTETICO_ejemplo_phyphox")
    assert ejemplo.resolver("otra/ruta.zip") == "otra/ruta.zip" and ejemplo.resolver(None) is None
    ruta = ejemplo.resolver("ejemplo")
    assert ruta == str(tmp_path / "SINTETICO_ejemplo_phyphox") and "SINTÉTICO" in capsys.readouterr().out
    with open(tmp_path / "SINTETICO_ejemplo_phyphox" / "Accelerometer.csv", encoding="utf-8") as f:
        assert next(csv.reader(f)) == ["Time (s)", "X (m/s^2)", "Y (m/s^2)", "Z (m/s^2)"]
    ejemplo.resolver("EJEMPLO")
    assert "Creando" not in capsys.readouterr().out            # no lo vuelve a generar
    assert main(["resumen", ruta]) == 0
    salida = capsys.readouterr().out
    assert "18 000" in salida and "100.0 Hz" in salida          # 3 min a 100 Hz, 1 min quieto al inicio y al final


def test_pin_fijo_por_entorno_y_redes_de_editor_para_docker(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PIN_MARCADOR", "2468")
    monkeypatch.setattr(config, "IPS_EDITOR", ["172.16.0.0/12", "no-es-ip"])
    from viaviva.app import crear_app
    ctx, c = _cliente(tmp_path, _base_con_calle(tmp_path), segundos=5, velocidad=5)
    try:
        assert ctx.pin == "2468"
        app = crear_app(ctx)

        async def pedir(ip):
            t = httpx.ASGITransport(app=app, client=(ip, 5000))
            async with httpx.AsyncClient(transport=t, base_url="http://x") as cli:
                return (await cli.get("/captura")).status_code, (await cli.post("/api/pin", json={"pin": "2468"}))

        cod, pin = asyncio.run(pedir("172.17.0.1"))            # puerta de enlace de Docker: editor (sin usuarios)
        assert cod == 200 and pin.status_code == 200
        cod, _ = asyncio.run(pedir("192.168.1.40"))             # otro equipo del WiFi: sin PIN no entra a /captura
        assert cod == 303
    finally:
        ctx.fuente.cerrar()


def test_ip_para_el_celular_en_docker(monkeypatch):
    from viaviva import doctor
    monkeypatch.delenv("VIAVIVA_IP_PC", raising=False)
    monkeypatch.setenv("VIAVIVA_EN_DOCKER", "1")
    assert doctor.ip_local() is None                           # la IP del contenedor no le sirve al celular
    monkeypatch.setenv("VIAVIVA_IP_PC", "172.20.10.3")
    assert doctor.ip_local() == "172.20.10.3"


def test_sesion_copiada_de_otro_pc_rehace_sus_etiquetas(tmp_path):
    from viaviva import sesiones
    ctx, c = _cliente(tmp_path, _base_con_calle(tmp_path), segundos=20, velocidad=40)
    try:
        c.post("/api/grabar", json={"accion": "iniciar", "nombre": "zip"})
        time.sleep(0.3)
        c.post("/api/etiqueta", json={"clase": "hueco"})
        ctx.fuente.terminada.wait(10)
        nombre = c.post("/api/grabar", json={"accion": "detener"}).json()["carpeta"]
    finally:
        ctx.fuente.cerrar()
    # «Otro PC»: solo la carpeta de la sesión (como sale de un zip), sin el CSV hermano
    otro = tmp_path / "otro_pc"
    shutil.copytree(tmp_path / "grab" / nombre, otro / nombre)
    assert not (otro / f"{nombre}_etiquetas.csv").exists()
    lista = sesiones.listar(otro)
    assert lista[0]["nombre"] == nombre and "error" not in lista[0]
    filas = (otro / f"{nombre}_etiquetas.csv").read_text(encoding="utf-8").splitlines()
    assert filas[0] == "t_s,clase" and [x.split(",")[1] for x in filas[1:]] == ["hueco"]
