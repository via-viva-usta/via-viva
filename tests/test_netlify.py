"""Netlify: netlify.toml publica web/en_linea y arma config.js en producción y en las vistas previas; tramos.geojson
está versionado y es válido; config.js (con claves) nunca entra a Git."""
import json
import subprocess
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ARMADO = "node herramientas/config_web.mjs"


def test_netlify_toml_publica_y_arma_config_en_todos_los_contextos():
    cfg = tomllib.loads((RAIZ / "netlify.toml").read_text(encoding="utf-8"))
    assert cfg["build"]["publish"] == "web/en_linea"
    assert cfg["build"]["command"] == ARMADO
    for contexto in ("deploy-preview", "branch-deploy"):
        assert cfg["context"][contexto]["command"] == ARMADO
    assert (RAIZ / "herramientas" / "config_web.mjs").exists()
    assert (RAIZ / "docs" / "PUBLICAR_WEB.md").exists()


def test_tramos_geojson_versionado_y_valido():
    ruta = RAIZ / "web" / "en_linea" / "datos" / "tramos.geojson"
    g = json.loads(ruta.read_text(encoding="utf-8"))
    assert g["type"] == "FeatureCollection" and len(g["features"]) > 100
    assert "OpenStreetMap" in g.get("fuente", "")
    assert all(f["geometry"]["type"] in ("LineString", "MultiLineString") for f in g["features"])
    r = subprocess.run(["git", "ls-files", "--error-unmatch", str(ruta.relative_to(RAIZ))], cwd=RAIZ,
                       capture_output=True)
    if r.returncode == 128 and b"not a git repository" in r.stderr:
        return                                             # copia sin .git (p. ej. un zip): solo se valida el archivo
    assert r.returncode == 0, "tramos.geojson debe estar en Git"


def test_config_js_no_va_en_git():
    r = subprocess.run(["git", "check-ignore", "-q", "web/en_linea/config.js"], cwd=RAIZ)
    assert r.returncode in (0, 128)                        # 0 = ignorado; 128 = no es un repo
