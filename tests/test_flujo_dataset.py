"""Flujo único del dataset por la API: grabar → sesiones → importar video (sincronía por destello) → revisar → dataset."""
import json
import time

import pytest

from tests.test_viaviva import _base_con_calle, _cliente


def _video_con_destello(ruta, inicio_s=4.0, segundos=12, fps=30):
    """Video gris con un destello de 3 s (blanco/negro cada 0,25 s) que empieza en `inicio_s`."""
    cv2 = pytest.importorskip("cv2")
    import numpy as np
    w = cv2.VideoWriter(str(ruta), cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 36))
    for k in range(segundos * fps):
        t = k / fps
        nivel = 90
        if inicio_s <= t < inicio_s + 3:
            nivel = 255 if int((t - inicio_s) / 0.25) % 2 == 0 else 0
        w.write(np.full((36, 64, 3), nivel, np.uint8))
    w.release()
    return ruta


def test_flujo_sesion_video_revision_dataset(tmp_path, monkeypatch):
    from viaviva import sesiones
    monkeypatch.setattr(sesiones, "SALIDA_DATASET", tmp_path / "ds")
    monkeypatch.setattr("viaviva.ventanas.SALIDAS", tmp_path / "ds")
    ctx, c = _cliente(tmp_path, _base_con_calle(tmp_path), segundos=40, velocidad=40)
    try:
        c.post("/api/grabar", json={"accion": "iniciar", "nombre": "flujo"})
        time.sleep(0.2)
        d = c.post("/api/destello", json={}).json()["destello"]
        ctx.fuente.terminada.wait(10)
        nombre = c.post("/api/grabar", json={"accion": "detener"}).json()["carpeta"]
    finally:
        ctx.fuente.cerrar()
    lista = c.get("/api/sesiones").json()["sesiones"]
    assert lista[0]["nombre"] == nombre and lista[0]["video"] is False and lista[0]["eventos_detectados"] == 3
    det = c.get(f"/api/sesiones/{nombre}").json()
    assert [round(e["t_s"]) for e in det["eventos"]] == [10, 20, 30] and len(det["trayecto"]) > 30
    assert len(det["envolvente"]) > 300 and det["destellos"] == [d["t_s"]]
    # Importar video: se sincroniza solo con el destello
    video = _video_con_destello(tmp_path / "IMG_0001.mp4")
    r = c.post(f"/api/sesiones/{nombre}/video?archivo=IMG_0001.mp4", content=video.read_bytes()).json()
    assert r["metodo"] == "destello" and abs(r["desfase_s"] - (d["t_s"] - 4.0)) < 0.1 and r["duracion_s"] == 12.0
    assert any("cubre solo" in a for a in r["avisos"])              # 12 s de video para 40 s de sesión: avisa
    ses = sesiones.carpeta(tmp_path / "grab", nombre)
    primero = sesiones.ruta_video(ses)
    assert primero and primero.exists()
    c.post(f"/api/sesiones/{nombre}/video?archivo=IMG_0001.mp4", content=video.read_bytes())
    actual = sesiones.ruta_video(ses)
    assert actual and actual != primero and actual.exists() and primero.exists()  # reemplazar conserva el anterior
    monkeypatch.setattr(sesiones, "MAX_VIDEO_BYTES", 1000)
    grande = c.post(f"/api/sesiones/{nombre}/video?archivo=IMG_0001.mp4", content=b"x" * 1001)
    assert grande.status_code == 413 and sesiones.ruta_video(ses) == actual and actual.exists()
    assert not list(ses.glob(".video-carga-*"))
    assert c.get(f"/api/sesiones/{nombre}/video").status_code == 200
    assert c.post(f"/api/sesiones/{nombre}/video?archivo=x.txt", content=b"hola").status_code == 400
    assert c.post(f"/api/sesiones/{nombre}/desfase", json={"desfase_s": 1.5}).json()["metodo"] == "manual"
    # Revisión: confirmar, corregir y descartar quedan en la base de la sesión y en las etiquetas
    ev = det["eventos"]
    rev = f"/api/sesiones/{nombre}/revision"
    assert c.post(rev, json={"t_s": ev[0]["t_s"], "decision": "confirmar", "clase": "hueco"}).json()["ok"]
    c.post(f"/api/sesiones/{nombre}/revision", json={"t_s": ev[1]["t_s"], "decision": "corregir", "clase": "resalto"})
    c.post(f"/api/sesiones/{nombre}/revision", json={"t_s": ev[2]["t_s"], "decision": "descartar"})
    assert c.post(rev, json={"t_s": 1, "decision": "confirmar", "clase": "nada"}).status_code == 400
    etq = (tmp_path / "grab" / f"{nombre}_etiquetas.csv").read_text(encoding="utf-8").splitlines()
    assert [x.split(",")[1] for x in etq[1:]] == ["hueco", "resalto", "via_buena"]
    det = c.get(f"/api/sesiones/{nombre}").json()
    assert det["revisados"] == 3 and det["eventos"][2]["revision"]["decision"] == "descartar"
    assert c.get("/api/sesiones/sesion_noexiste").status_code == 400 and c.get("/api/sesiones/..%2F..").status_code in (400, 404)
    # Dataset: construir y ver calidad y umbrales
    r = sesiones.construir_dataset(tmp_path / "grab")
    assert r["sesiones"] == 1 and r["por_clase"]["hueco"] >= 2 and r["detector"]["global"]["tp"] == 2
    assert "error" in r["calibracion"] and any("no son concluyentes" in a for a in r["avisos"])
    assert c.get("/api/dataset").json()["ultimo"]["ventanas"] == r["ventanas"]
    assert json.loads((tmp_path / "ds" / "ultimo.json").read_text(encoding="utf-8"))["sesiones"] == 1
    for pagina in ("/sesiones", "/revision", "/dataset", "/demo", "/captura", "/tablero"):
        assert c.get(pagina).status_code == 200


def test_video_sin_destello_usa_la_fecha_del_archivo(tmp_path):
    import struct

    from viaviva import sesiones
    f = tmp_path / "v.mov"                      # .mov mínimo: solo el átomo moov/mvhd con fecha de creación
    creado = 1794054010 + 2082844800
    mvhd = b"mvhd" + bytes(4) + struct.pack(">I", creado) + bytes(88)
    f.write_bytes(struct.pack(">I4s", 8, b"ftyp") + struct.pack(">I", 8 + 4 + len(mvhd)) + b"moov"
                  + struct.pack(">I", 4 + len(mvhd)) + mvhd)
    assert sesiones._creacion_mov(f) == 1794054010
    assert sesiones._creacion_mov(tmp_path / "no.mov") is None
