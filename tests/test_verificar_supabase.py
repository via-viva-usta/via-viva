"""herramientas/verificar_supabase.py: revisión del SQL (sin red) y de la RLS contra un PostgREST FALSO.

El servidor falso imita lo que hace Supabase con la RLS de viaviva/supabase_esquema.sql: la clave secreta salta la
RLS; la anon sin sesión lee [] y no escribe (401). La variante `abierta` simula una RLS mal puesta.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from herramientas import verificar_supabase as v

SECRETA, PUBLICA = "clave-secreta-prueba", "clave-publica-prueba"


class _PostgrestFalso:
    def __init__(self, abierta=False):
        filas: dict[str, list[dict]] = {}
        self.filas = filas

        class M(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _responder(self, estado, cuerpo=None):
                datos = b"" if cuerpo is None else json.dumps(cuerpo).encode()
                self.send_response(estado)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(datos)

            def _rol(self):
                clave = self.headers["apikey"]
                return "service" if clave == SECRETA else ("anon" if clave == PUBLICA else None)

            def _tabla_y_filtro(self):
                u = urlparse(self.path)
                q = parse_qs(u.query)
                ide = q.get("id_origen", [""])[0]
                return u.path.rsplit("/", 1)[-1], ide

            def _coinciden(self, tabla, ide):
                todas = filas.get(tabla, [])
                if ide.startswith("eq."):
                    return [f for f in todas if f["id_origen"] == ide[3:]]
                if ide.startswith("like."):
                    return [f for f in todas if f["id_origen"].startswith(ide[5:].rstrip("*"))]
                return todas

            def do_GET(self):
                rol = self._rol()
                tabla, ide = self._tabla_y_filtro()
                visibles = self._coinciden(tabla, ide) if (rol == "service" or abierta) else []
                self._responder(200 if rol else 401, visibles if rol else None)

            def do_POST(self):
                rol = self._rol()
                tabla, _ = self._tabla_y_filtro()
                nuevas = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if rol == "service" or (abierta and rol):
                    filas.setdefault(tabla, []).extend(nuevas)
                    return self._responder(201, nuevas)
                self._responder(401, {"code": "42501", "message": "new row violates row-level security policy"})

            def do_DELETE(self):
                rol = self._rol()
                tabla, ide = self._tabla_y_filtro()
                if rol == "service" or (abierta and rol):
                    borrar = self._coinciden(tabla, ide)
                    filas[tabla] = [f for f in filas.get(tabla, []) if f not in borrar]
                    return self._responder(200, borrar)
                self._responder(200, [])                    # RLS: borra 0 filas, sin error

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), M)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"


def test_el_esquema_del_repo_pasa_la_revision_sql():
    r = v.revisar_sql(v.ESQUEMA.read_text(encoding="utf-8"))
    assert all(ok for ok, _ in r), [t for ok, t in r if not ok]


def test_la_revision_sql_detecta_una_politica_abierta():
    malo = v.ESQUEMA.read_text(encoding="utf-8") + '\ncreate policy "todos" on eventos_publicos for select to anon using (true);'
    fallas = [t for ok, t in v.revisar_sql(malo) if not ok]
    assert any("anon" in t for t in fallas) and any("using (true)" in t for t in fallas)


def test_proyecto_con_rls_correcta_pasa_y_borra_la_fila_de_prueba():
    nube = _PostgrestFalso()
    r = v.revisar_proyecto(nube.url, PUBLICA, SECRETA)
    assert all(ok for ok, _ in r), [t for ok, t in r if not ok]
    assert nube.filas.get("eventos_publicos") == []
    nube.srv.shutdown()


def test_proyecto_con_rls_abierta_falla():
    nube = _PostgrestFalso(abierta=True)
    fallas = [t for ok, t in v.revisar_proyecto(nube.url, PUBLICA, SECRETA) if not ok]
    assert any("NO lee eventos_publicos" in t for t in fallas)
    assert any("NO escribe" in t for t in fallas)
    nube.srv.shutdown()


def test_main_sin_claves_no_toca_la_red(tmp_path, monkeypatch, capsys):
    for k in ("SUPABASE_URL", "SUPABASE_CLAVE_PUBLICA", "SUPABASE_CLAVE"):
        monkeypatch.delenv(k, raising=False)
    assert v.main(["--env", str(tmp_path / "no_existe.env")]) == 2
    salida = capsys.readouterr().out
    assert "Faltan en el .env" in salida and SECRETA not in salida


def test_main_nunca_imprime_las_claves(tmp_path, monkeypatch, capsys):
    nube = _PostgrestFalso()
    env = tmp_path / ".env"
    env.write_text(f"SUPABASE_URL={nube.url}\nSUPABASE_CLAVE_PUBLICA={PUBLICA}\nSUPABASE_CLAVE={SECRETA}\n",
                   encoding="utf-8")
    for k in ("SUPABASE_URL", "SUPABASE_CLAVE_PUBLICA", "SUPABASE_CLAVE"):
        monkeypatch.delenv(k, raising=False)
    assert v.main(["--env", str(env)]) == 0
    salida = capsys.readouterr().out
    assert "Todo OK" in salida and SECRETA not in salida and PUBLICA not in salida
    nube.srv.shutdown()
