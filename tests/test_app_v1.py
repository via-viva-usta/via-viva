"""App v1: marca compartida con la web de Dany, mapa sin internet, panel de conexión, cambio de fuente y cámara."""
import json
import time

import pytest

from tests.test_viaviva import _base_con_calle, _cliente
from viaviva import config


def _esperar(cond, segundos=15.0):
    fin = time.monotonic() + segundos
    while time.monotonic() < fin:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_marca_de_dany_y_app_instalable(tmp_path):
    ctx, c = _cliente(tmp_path, _base_con_calle(tmp_path), segundos=5, velocidad=5)
    try:
        css = c.get("/marca.css")
        assert css.status_code == 200 and "--t-fondo" in css.text and "--vv-detectado" in css.text
        assert "vv_tema" in c.get("/tema.js").text                      # misma llave del tema que la web en línea
        assert c.get("/fuentes/inter.woff2").status_code == 200
        assert c.get("/fuentes/..%2F..%2F.env").status_code == 404
        m = c.get("/manifest.webmanifest").json()
        assert m["short_name"] == "VÍA VIVA" and m["display"] == "standalone"
        assert "openfreemap" in c.get("/sw.js").text
        for pagina in ("captura", "sesiones", "dataset", "tablero", "demo", "marcar", "sync", "entrar", "camara"):
            html = c.get("/" + pagina).text
            assert '/marca.css' in html and '/tema.js' in html, pagina   # un solo sistema de estilos
            assert 'class="tema-a"' not in html and "fonts.googleapis" not in html
    finally:
        ctx.fuente.cerrar()
    estilo = (config.RAIZ / "viaviva" / "web" / "estilo.css").read_text(encoding="utf-8")
    assert "fonts.googleapis" not in estilo and "var(--t-fondo)" in estilo


def test_calles_para_el_mapa_sin_internet(tmp_path):
    ctx, c = _cliente(tmp_path, _base_con_calle(tmp_path), segundos=5, velocidad=5)
    try:
        r = c.get("/api/calles").json()
        assert "base local" in r["fuente"] and r["calles"][0][1][0] == [5.535, -73.37]   # [tipo, [[lat, lon]...]]
    finally:
        ctx.fuente.cerrar()
    repo = json.loads((config.RAIZ / "viaviva" / "web" / "datos" / "calles_tunja.json").read_text(encoding="utf-8"))
    assert len(repo["calles"]) > 5000 and "OpenStreetMap" in repo["fuente"]                # sin base: las del repo
    ruta = json.loads((config.RAIZ / "viaviva" / "web" / "datos" / "ruta_ejemplo.json").read_text(encoding="utf-8"))
    assert 5000 < ruta["largo_m"] < 6500 and len(ruta["puntos"]) > 50


def test_panel_de_conexion_y_cambio_de_fuente(tmp_path, monkeypatch):
    from viaviva import ejemplo
    monkeypatch.setattr(ejemplo, "CARPETA", tmp_path / "SINTETICO_ejemplo_phyphox")
    ctx, c = _cliente(tmp_path, _base_con_calle(tmp_path), segundos=5, velocidad=5)
    try:
        assert c.post("/api/conexion/fuente", json={"tipo": "ejemplo"}).json() == {"ok": True, "fuente": "ejemplo"}
        assert _esperar(lambda: ctx.n.n_acc > 200, 20)
        time.sleep(1.2)
        f = c.get("/api/conexion").json()
        assert f["fuente"]["tipo"] == "ejemplo" and f["fuente"]["simulador"] and f["fuente"]["puerto"]
        assert f["fuente"]["conectado"] and f["marcar"]["url_qr"].endswith("?pin=" + ctx.pin)
        assert c.get("/api/estado").json()["fuente"] == "ejemplo"
        assert c.get("/api/conexion").json()["fuente"]["hz_real"] > 50              # llegan muestras de verdad
        p = c.post("/api/conexion/probar", json={}).json()
        assert p["phyphox"]["ok"] and p["phyphox"]["latencia_ms"] is not None and "red" in p and "pi" in p
        svg = c.get("/api/marcar/qr.svg")
        assert svg.status_code == 200 and svg.text.lstrip().startswith("<svg")
        c.post("/api/grabar", json={"accion": "iniciar"})
        r = c.post("/api/conexion/fuente", json={"tipo": "ninguna"})
        assert r.status_code == 400 and "detenga la grabación" in r.json()["error"]
        c.post("/api/grabar", json={"accion": "detener"})
        assert c.post("/api/conexion/fuente", json={"tipo": "ninguna"}).json()["fuente"] == "ninguna"
        assert c.post("/api/conexion/fuente", json={"tipo": "otra"}).status_code == 400
    finally:
        ctx.cerrar()


def test_probar_phyphox_sin_iphone_explica_que_revisar():
    from viaviva import conexion
    r = conexion.probar_phyphox("http://127.0.0.1:9", timeout=0.3)
    assert not r["ok"] and "80 y 8080" in r["mensaje"] and len(r["intentos"]) >= 2


def test_video_en_vivo_por_partes_y_cuadro_del_celular(tmp_path):
    ctx, c = _cliente(tmp_path, _base_con_calle(tmp_path), segundos=20, velocidad=2)
    try:
        sin = c.post("/api/camara/parte?id=video123&n=0&tipo=video/webm", content=b"x")
        assert sin.status_code == 409                                              # sin grabación abierta
        nombre = c.post("/api/grabar", json={"accion": "iniciar"}).json()["carpeta"]
        inicio = time.time() + 0.5
        r0 = c.post(f"/api/camara/parte?id=video123&n=0&tipo=video/mp4&inicio={inicio}&origen=pc", content=b"AAAA")
        assert r0.status_code == 200 and r0.json()["archivo"].endswith(".mp4")
        assert c.post("/api/camara/parte?id=video123&n=2&tipo=video/mp4", content=b"C").status_code == 400  # falta la 1
        assert c.post("/api/camara/parte?id=video123&n=1&tipo=video/mp4", content=b"BB").json()["bytes"] == 6
        fin = c.post("/api/camara/fin?id=video123").json()
        assert fin["bytes"] == 6
        from viaviva import sesiones
        carpeta = sesiones.carpeta(tmp_path / "grab", nombre)
        v = json.loads((carpeta / "video.json").read_text(encoding="utf-8"))
        assert v["metodo"] == "en_vivo" and v["origen_video"] == "pc" and 0.0 <= v["desfase_s"] < 3.0
        assert (carpeta / v["archivo"]).read_bytes() == b"AAAABB" and v["en_curso"] is False
        assert c.get(f"/api/sesiones/{nombre}/video").status_code == 200
        # vista previa del celular
        assert c.post("/api/camara/cuadro", content=b"no-es-jpeg").status_code == 400
        assert c.post("/api/camara/cuadro?origen=celular", content=b"\xff\xd8\xff\xe0jpeg").json()["ok"]
        ver = c.get("/api/camara/cuadro.jpg")
        assert ver.status_code == 200 and ver.headers["content-type"] == "image/jpeg"
        c.post("/api/grabar", json={"accion": "detener"})
    finally:
        ctx.fuente.cerrar()


def test_https_local_para_la_camara_del_celular(tmp_path):
    pytest.importorskip("cryptography")
    from cryptography import x509

    from viaviva import camara
    cert, clave = camara.certificado_servidor(["172.20.10.3"], tmp_path)
    hoja = x509.load_pem_x509_certificate(cert.read_bytes())
    ips = [str(i) for i in hoja.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
           .get_values_for_type(x509.IPAddress)]
    assert "172.20.10.3" in ips and "127.0.0.1" in ips
    dias = (hoja.not_valid_after_utc - hoja.not_valid_before_utc).days
    assert dias <= 825                                                      # límite de iOS para servidores
    ca = x509.load_der_x509_certificate(camara.ca_der(tmp_path))
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert camara.autoridad(tmp_path)[0].serial_number == ca.serial_number   # la autoridad se reutiliza


def test_latido_de_la_ventana_y_reinicio_de_fuente(tmp_path):
    ctx, c = _cliente(tmp_path, _base_con_calle(tmp_path), segundos=5, velocidad=5)
    try:
        assert ctx.latido is None
        c.post("/api/latido")
        assert ctx.latido is not None                                      # TestClient cuenta como este PC
        ctx.n.iniciar_grabacion("x")
        with pytest.raises(ValueError):
            ctx.n.reiniciar_fuente(100.0, "simulado", "x")
        ctx.n.detener_grabacion()
    finally:
        ctx.fuente.cerrar()
    from viaviva import ventana
    assert ventana.navegador_app() is None or isinstance(ventana.navegador_app(), str)
