"""Lo propio de macOS en el doctor: batería con `pmset` y el texto del firewall (sin necesitar un Mac)."""
from viaviva import doctor

PMSET_BATERIA = ("Now drawing from 'Battery Power'\n"
                 " -InternalBattery-0 (id=4653155)\t42%; discharging; 3:10 remaining present: true\n")
PMSET_CARGANDO = ("Now drawing from 'AC Power'\n"
                  " -InternalBattery-0 (id=4653155)\t87%; charging; 0:35 remaining present: true\n")
PMSET_ESCRITORIO = "Now drawing from 'AC Power'\n"


def test_pmset_con_bateria_sin_cargador():
    assert doctor.bateria_pmset(PMSET_BATERIA) == (42, False)


def test_pmset_cargando():
    assert doctor.bateria_pmset(PMSET_CARGANDO) == (87, True)


def test_pmset_mac_de_escritorio():
    assert doctor.bateria_pmset(PMSET_ESCRITORIO) == (None, None)


def test_texto_firewall_por_sistema(monkeypatch):
    for sistema, palabra in (("Windows", "Firewall de Windows"), ("Darwin", "macOS"), ("Linux", "firewall")):
        monkeypatch.setattr(doctor.platform, "system", lambda s=sistema: s)
        assert palabra in doctor.texto_firewall()
    monkeypatch.setattr(doctor.platform, "system", lambda: "Darwin")
    assert "Windows" not in doctor.texto_firewall()
