"""herramientas/pi_probar.sh y actualizar_pi.sh: sintaxis de Bash y reglas clave (sin hardware: no se ejecutan)."""
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS = [RAIZ / "herramientas" / "pi_probar.sh", RAIZ / "herramientas" / "actualizar_pi.sh"]


@pytest.mark.parametrize("ruta", SCRIPTS, ids=lambda p: p.name)
def test_sintaxis_bash(ruta):
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash no está disponible")
    assert b"\r\n" not in ruta.read_bytes(), "debe tener fin de línea LF"
    r = subprocess.run([bash, "-n", str(ruta)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_pi_probar_cubre_el_checklist():
    t = SCRIPTS[0].read_text(encoding="utf-8")
    for clave in ("get_throttled", "/dev/spidev0.0", "0xE5", "NMEA", "PI_PIN_LED:-22", "via-viva-pi", "trap volver EXIT"):
        assert clave in t


@pytest.mark.parametrize("ruta", SCRIPTS, ids=lambda p: p.name)
def test_sin_grep_q_en_tuberias_con_pipefail(ruta):
    """Con `set -o pipefail`, `cmd | grep -q` puede dar 141 (SIGPIPE) aunque haya coincidencia (falso «no instalado»)."""
    t = ruta.read_text(encoding="utf-8")
    if "pipefail" in t:
        lineas = [x for x in t.splitlines() if not x.lstrip().startswith("#")]
        assert not any("| grep -q" in x for x in lineas)


def test_actualizar_pi_solo_avanza_en_main_y_tiene_vuelta_atras():
    t = SCRIPTS[1].read_text(encoding="utf-8")
    assert "git pull --ff-only origin main" in t
    assert '[ "$rama" != main ]' in t
    assert 'git reset --hard "$anterior"' in t
    assert "push" not in t.replace("nunca se empuja", "")
