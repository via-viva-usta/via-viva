"""Nodo central Raspberry Pi (pi/): estructuras, detector, GPS, núcleo + reproducción, servidor y sincronización.
Todo corre en el PC sin hardware (los sensores reales se validan en la placa)."""
import json
import math
import random
import sqlite3
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from pi import almacen, config
from pi.estructuras import (BuferCircular, Cola, GrafoCalles, IndiceGeohash, MonticuloMax, TablaHash, geohash,
                            top_k, vecinos_geohash)
from pi.nucleo import Detector, Nucleo, Welford
from pi.sensores import ParserNMEA, suma_nmea_ok


# ------------------------------------------------------------------------------------------------ estructuras
def test_bufer_circular_sobrescribe_lo_mas_viejo():
    b = BuferCircular(3)
    for i in range(5):
        b.agregar(i)
    assert list(b) == [2, 3, 4] and b[-1] == 4 and b[0] == 2 and b.sobrescritos == 2 and b.ultimos(2) == [3, 4]


def test_cola_fifo():
    c = Cola()
    for i in range(100):
        c.encolar(i)
    assert [c.desencolar() for _ in range(60)] == list(range(60)) and len(c) == 40
    c.encolar(100)
    assert [c.desencolar() for _ in range(41)] == list(range(60, 101))
    with pytest.raises(IndexError):
        c.desencolar()


def test_tabla_hash_igual_a_dict():
    rnd = random.Random(7)
    t, d = TablaHash(), {}
    for _ in range(5000):
        k = rnd.choice([rnd.randint(0, 300), f"g{rnd.randint(0, 300)}", (rnd.randint(0, 9), True)])
        op = rnd.random()
        if op < 0.6:
            v = rnd.random()
            t.poner(k, v)
            d[k] = v
        elif op < 0.8:
            assert t.quitar(k) == (d.pop(k, None) is not None)
        else:
            assert t.sumar(("c", 1)) == d.setdefault(("c", 1), 0) + 1
            d[("c", 1)] += 1
    assert len(t) == len(d) and dict(t.items()) == d
    assert t.cubeta_mas_larga() <= 8


def test_monticulo_top_k_igual_a_ordenar():
    rnd = random.Random(3)
    xs = [rnd.random() for _ in range(1000)]
    assert top_k(xs, 10, lambda x: x) == sorted(xs, reverse=True)[:10]
    m = MonticuloMax(lambda x: -x)
    for x in xs[:50]:
        m.insertar(x)
    assert [m.extraer() for _ in range(50)] == sorted(xs[:50])


def test_geohash_igual_al_etl_y_vecinos():
    from etl.geohash import codificar
    for lat, lon in [(5.5353, -73.3678), (5.56, -73.34), (-33.9, 151.2)]:
        assert geohash(lat, lon, 7) == codificar(lat, lon, 7)
    v = vecinos_geohash(geohash(5.5353, -73.3678, 7))
    assert len(set(v)) == 9 and geohash(5.5353, -73.3678, 7) in v


def test_grafo_corredor_y_zonas():
    g = GrafoCalles()                      # camino 1-2-3-4-5 y un tramo suelto 9-10
    for t, (u, v) in enumerate([(1, 2), (2, 3), (3, 4), (4, 5), (9, 10)], start=100):
        g.agregar_tramo(t, u, v)
    assert g.corredor(102, 1) == {102: 0, 101: 1, 103: 1}
    assert g.corredor(100, 2) == {100: 0, 101: 1, 102: 2}
    z = g.zonas({100, 101, 103, 104})                  # 102 no está marcado: 103 queda aparte; 104 está suelto
    assert z[0] == [100, 101] and sorted(z[1:]) == [[103], [104]]


def test_indice_geohash_encuentra_la_calle():
    idx = IndiceGeohash()
    idx.agregar(1, [(5.5350, -73.3700), (5.5350, -73.3600)])   # calle este-oeste de ~1,1 km
    idx.agregar(2, [(5.5400, -73.3650), (5.5450, -73.3650)])
    t, d = idx.mas_cercano(5.53508, -73.3650)                  # ~9 m al norte de la calle 1, en la mitad
    assert t == 1 and 8 < d < 10
    assert idx.mas_cercano(5.5380, -73.3650)[0] is None        # a > 25 m de todo


# ------------------------------------------------------------------------------------------------ detector
def test_parametros_iguales_a_analysis():
    pytest.importorskip("pandas")
    from analysis.detector_umbral import ParametrosUmbral as P
    assert vars(P()) == vars(config.ParametrosUmbral())


def test_detector_igual_al_de_la_captura_en_vivo():
    from herramientas.captura_phyphox_remoto import DetectorEnVivo
    rnd = random.Random(1)
    a, b = Detector(100.0), DetectorEnVivo(100.0)
    for i in range(3000):
        x = rnd.gauss(0, 0.02) + (0.9 if i % 700 == 650 else 0)
        assert a.muestra(x, 20.0) == b.muestra(x, 20.0)


def test_welford():
    w = Welford()
    for x in [2, 4, 4, 4, 5, 5, 7, 9]:
        w.agregar(x)
    assert w.media == 5 and abs(w.desv - 2.138) < 1e-3


# ------------------------------------------------------------------------------------------------ GPS
def _nmea(cuerpo: str) -> str:
    x = 0
    for c in cuerpo:
        x ^= ord(c)
    return f"${cuerpo}*{x:02X}"


def test_parser_nmea():
    p = ParserNMEA()
    assert p.linea(_nmea("GPGGA,123519,0532.118,N,07322.068,W,1,08,0.9,2810.0,M,0,M,,")) is None
    r = p.linea(_nmea("GPRMC,123519.50,A,0532.118,N,07322.068,W,010.0,084.4,071126,,,A"))
    assert r["valido"] and abs(r["lat"] - (5 + 32.118 / 60)) < 1e-9 and abs(r["lon"] + (73 + 22.068 / 60)) < 1e-9
    assert abs(r["vel_ms"] - 5.14444) < 1e-4 and r["sat"] == 8 and r["alt"] == 2810.0
    assert r["utc_epoch"] == 1794054919.5         # 2026-11-07 12:35:19.5 UTC
    assert not suma_nmea_ok("$GPRMC,1*00") and p.linea("basura") is None
    sin_fix = p.linea(_nmea("GPRMC,123520,V,,,,,,,071126,,,N"))
    assert not sin_fix["valido"] and math.isnan(sin_fix["lat"])


# ------------------------------------------------------------------------------------------------ núcleo + reproducción
def _export_sintetico(carpeta: Path, segundos: float = 40.0, fs: float = 100.0) -> Path:
    """Export tipo phyphox iOS: carro a 18 km/h por la calle (5.5350, -73.37 → -73.36) con 3 golpes."""
    carpeta.mkdir(parents=True)
    rnd = random.Random(5)
    n = int(segundos * fs)
    with open(carpeta / "Accelerometer.csv", "w", encoding="utf-8") as f:
        f.write('"Time (s)","X (m/s^2)","Y (m/s^2)","Z (m/s^2)"\n')
        for i in range(n):
            t = i / fs
            golpe = 12.0 if any(abs(t - tg) < 0.03 for tg in (10.0, 20.0, 30.0)) else 0.0
            f.write(f"{t:.4f},{rnd.gauss(0, 0.1):.4f},{rnd.gauss(0, 0.1):.4f},{9.81 + rnd.gauss(0, 0.15) + golpe:.4f}\n")
    with open(carpeta / "Location.csv", "w", encoding="utf-8") as f:
        f.write('"Time (s)","Latitude (°)","Longitude (°)","Height (m)","Velocity (m/s)","Direction (°)",'
                '"Horizontal Accuracy (m)","Vertical Accuracy (°)"\n')
        for s in range(int(segundos)):
            f.write(f"{s},{5.5350},{-73.37 + s * 0.000045:.6f},2800,5.0,90,4,3\n")
    (carpeta / "meta").mkdir()
    (carpeta / "meta" / "time.csv").write_text('"event","experiment time","system time","system time text"\n'
                                               '"START",0,1794054000.0,"x"\n', encoding="utf-8")
    return carpeta


def _base_con_calle(tmp_path: Path) -> str:
    url = f"sqlite:///{(tmp_path / 'pi.db').as_posix()}"
    con = almacen.conectar(url)
    con.execute("INSERT INTO tramos (osm_u, osm_v, nombre, tipo_via, longitud_m, lat_centro, lon_centro, geohash7, "
                "geometria_wkt, fecha_carga) VALUES (1, 2, 'Calle de prueba', 'primary', 1100, 5.535, -73.365, "
                "'d2g6', 'LINESTRING (-73.3700 5.5350, -73.3600 5.5350)', 'x')")
    con.execute("INSERT INTO riesgo (id_tramo, modelo, version_modelo, fecha_calculo, probabilidad, rango, reportado, "
                "fuente_etiquetas) VALUES (1, 'bosque', 'v-prueba', '2026-11-07T00:00:00Z', 0.8, 1, 1, 'planb')")
    con.execute("INSERT INTO reportes (canal, ts_utc, lat, lon, tipo, id_tramo, ts_carga) VALUES "
                "('web', '2026-11-07T10:00:00Z', 5.535, -73.365, 'hueco', 1, 'x')")
    con.commit()
    con.close()
    return url


def _url(srv, ruta):
    return f"http://127.0.0.1:{srv.server_address[1]}{ruta}"


def _post(srv, ruta, cuerpo, cabeceras=None):
    req = urllib.request.Request(_url(srv, ruta), data=json.dumps(cuerpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **(cabeceras or {})})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())


def test_servidor_reproduce_graba_detecta_y_guarda(tmp_path, monkeypatch):
    from pi.servidor import construir, crear_manejador
    monkeypatch.setenv("TABLERO_CLAVE", "")
    url = _base_con_calle(tmp_path)
    exp = _export_sintetico(tmp_path / "export")
    app = construir("reproducir", str(exp), velocidad=40, url_db=url, dir_grabaciones=tmp_path / "grab", sync=False)
    app.calles.listo.wait(10)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), crear_manejador(app))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert _post(srv, "/api/grabar", {"accion": "iniciar", "nombre": "prueba"})["ok"]
        app.fuente.terminada.wait(10)
        assert app.n.n_eventos_total == 3                     # los 3 golpes, ninguno falso
        ev = app.n.eventos.ultimos(3)
        assert [round(e["t_s"]) for e in ev] == [10, 20, 30] and all(e["id_tramo"] == 1 for e in ev)
        _post(srv, "/api/etiqueta", {"clase": "hueco"})       # t ≈ 40 s: lejos de los eventos → no se asigna
        carpeta = _post(srv, "/api/grabar", {"accion": "detener"})["carpeta"]
        estado = json.loads(urllib.request.urlopen(_url(srv, "/api/estado")).read())
        assert not estado["grabando"] and estado["latencias"]["detector_us"]["n"] == 4000
        con = sqlite3.connect(tmp_path / "pi.db")
        filas = con.execute("SELECT origen, id_nodo, clase, id_tramo, ts_utc FROM eventos ORDER BY ts_utc").fetchall()
        assert len(filas) == 3 and {f[:4] for f in filas} == {("simulado", "reproduccion", "impacto_fuerte", 1)}
        assert filas[0][4][:19] in ("2026-11-07T12:20:09", "2026-11-07T12:20:10")   # hora del export, no la del PC
        # La grabación queda en formato phyphox: se puede volver a reproducir
        from pi.fuentes import FuenteReproduccion
        grab = tmp_path / "grab" / carpeta
        f2 = FuenteReproduccion(grab)
        assert f2.fs == 100.0 and len(f2.tablas["acc"]) > 3000 and len(f2.tablas["gps"]) > 30
        assert (tmp_path / "grab" / f"{carpeta}_etiquetas.csv").read_text(encoding="utf-8").count("hueco") == 1
        # Tablero
        r = json.loads(urllib.request.urlopen(_url(srv, "/api/tablero/riesgo")).read())
        assert r["top10"][0]["nombre"] == "Calle de prueba" and r["corrida"]["demo"] is False
        p = json.loads(urllib.request.urlopen(_url(srv, "/api/tablero/peligros")).read())
        reporte = next(x for x in p["top"] if x["tipo_fila"] == "reporte")
        assert reporte["prioridad"] == 3 * 3 * 1 and p["top"][0]["tipo_fila"] == "reporte"  # lo real antes que lo simulado
        assert _post(srv, "/api/tablero/reportes/1/estado", {"estado": "en_reparacion"})["ok"]  # desde la misma máquina
    finally:
        srv.shutdown()
        app.fuente.cerrar()


def test_cambiar_estado_exige_clave(tmp_path, monkeypatch):
    from pi.servidor import construir, crear_manejador
    monkeypatch.setenv("TABLERO_CLAVE", "clave-de-prueba")
    url = _base_con_calle(tmp_path)
    app = construir("reproducir", str(_export_sintetico(tmp_path / "e", 5)), velocidad=50, url_db=url,
                    dir_grabaciones=tmp_path / "g", sync=False)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), crear_manejador(app))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with pytest.raises(urllib.error.HTTPError) as e:
            _post(srv, "/api/tablero/reportes/1/estado", {"estado": "reparado"}, {"X-Clave": "otra"})
        assert e.value.code == 403
        assert _post(srv, "/api/tablero/reportes/1/estado", {"estado": "reparado"}, {"X-Clave": "clave-de-prueba"})["ok"]
    finally:
        srv.shutdown()
        app.fuente.cerrar()


# ------------------------------------------------------------------------------------------------ sincronización
class _NubeFalsa:
    """Imita la API REST de Supabase: falla las primeras `fallas` peticiones y luego guarda lo recibido."""

    def __init__(self, fallas: int):
        self.fallas, self.recibido = fallas, []
        nube = self

        class M(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if nube.fallas > 0:
                    nube.fallas -= 1
                    self.send_response(503)
                else:
                    assert self.headers["apikey"] == "clave-prueba" and "on_conflict=id_origen" in self.path
                    nube.recibido.append((self.path.split("?")[0], cuerpo))
                    self.send_response(201)
                self.end_headers()
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), M)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"


def test_sincronizacion_cola_reintentos_y_lista_blanca(tmp_path):
    from pi import sincronizacion as s
    url = _base_con_calle(tmp_path)
    viejo = "2026-11-01T00:00:00Z"
    con = almacen.conectar(url)
    con.executemany("INSERT INTO eventos (id_nodo, hash_vehiculo, ts_utc, lat, lon, velocidad_kmh, clase, origen, "
                    "etiqueta_manual, foto_ruta, ts_carga) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    [("pi-01", "h-carro", "2026-11-07T10:00:00.000Z", 5.5350123, -73.365, 22.0, "hueco", "nodo",
                      "hueco", "x.jpg", viejo),
                     ("reproduccion", None, "2026-11-07T10:00:01.000Z", 5.535, -73.365, 20.0, "hueco", "simulado",
                      None, None, viejo)])
    con.execute("INSERT INTO riesgo (id_tramo, modelo, version_modelo, fecha_calculo, probabilidad) "
                "VALUES (1, 'logistica', 'DEMO-SINTETICO', '2026-11-05T00:00:00Z', 0.5)")
    con.commit()
    con.close()
    nube = _NubeFalsa(fallas=1)
    sin = s.Sincronizador(url=nube.url, clave="clave-prueba", url_db=url)
    r1 = sin.una_vez()                                        # encola 1 evento real + 1 riesgo real; la red falla
    assert r1["encolados"] == 2 and r1["enviados"] == 0 and r1["pendientes"] == {"eventos": 1, "riesgo": 1}
    r2 = sin.una_vez()                                        # el evento espera 30 s; el riesgo (no intentado) sale
    assert r2["enviados"] == 1 and r2["pendientes"] == {"eventos": 1}
    con = almacen.conectar(url)
    con.execute("UPDATE cola_envio SET proximo_intento = ''")   # pasó la espera
    con.commit()
    con.close()
    r3 = sin.una_vez()
    assert r3["enviados"] == 1 and r3["pendientes"] == {} and r3["enviados_total"] == {"eventos": 1, "riesgo": 1}
    tablas = {t: c for t, c in nube.recibido}
    ev = tablas["/rest/v1/eventos_publicos"][0]
    assert set(ev) == {"id_origen", "ts_utc", "lat", "lon", "clase", "etiquetado", "id_tramo", "geohash7", "origen",
                       "modelo_version"}                      # sin velocidad, vehículo, foto ni etiqueta en texto
    assert ev["lat"] == 5.53501 and ev["etiquetado"] is True
    rg = tablas["/rest/v1/riesgo_publico"][0]
    assert "reportado" not in rg and "variables_json" not in rg and rg["version_modelo"] == "v-prueba"
    assert sin.una_vez()["encolados"] == 0                    # nada se envía dos veces
    nube.srv.shutdown()


def test_sin_claves_no_sale_nada(tmp_path):
    from pi import sincronizacion as s
    sin = s.Sincronizador(url="", clave="", url_db=_base_con_calle(tmp_path))
    r = sin.una_vez()
    assert not r["configurado"] and r["enviados"] == 0 and r["pendientes"] == {"riesgo": 1}
