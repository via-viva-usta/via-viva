"""Pruebas del conversor de vueltas del cronómetro a etiquetas (analysis/vueltas_a_etiquetas.py)."""
import pytest

from analysis.vueltas_a_etiquetas import a_etiquetas, convertir, duracion_s, intervalos_parada, leer_vueltas


@pytest.mark.parametrize("texto,esperado", [("1:02.40", 62.4), ("62.4", 62.4), ("62,4", 62.4), ("00:01:02,40", 62.4),
                                            ("0:00.50", 0.5), ("1:00:05", 3605)])
def test_duraciones(texto, esperado):
    assert duracion_s(texto) == pytest.approx(esperado)


def test_suma_acumulada_y_sinonimos():
    v = leer_vueltas(["1:02.40 hueco", "0:33.10 Reductor", "Vuelta 3  00:12,50  Bache", "# comentario", ""])
    assert a_etiquetas(v) == [(62.4, "hueco"), (95.5, "resalto"), (108.0, "hueco")]


def test_paradas_e_intervalos():
    filas = a_etiquetas(leer_vueltas(["10 parada_inicio", "30 parada_fin", "5 hueco"]))
    assert intervalos_parada([t for t, _ in filas], [c for _, c in filas]) == [(10.0, 40.0)]


@pytest.mark.parametrize("lineas", [["5 parada_fin"], ["5 parada_inicio"], ["5 parada_inicio", "5 parada_inicio"],
                                    ["5 crater"], ["5"], ["abc hueco"]])
def test_errores(lineas):
    with pytest.raises(ValueError):
        a_etiquetas(leer_vueltas(lineas))


def test_archivo_e_invertir(tmp_path):
    txt = tmp_path / "2026-11-06_ruta1_pipe_vueltas.txt"
    txt.write_text("0:10.00 resalto\n0:05.00 hueco\n", encoding="utf-8")
    salida = convertir(txt, invertir=True)
    assert salida.name == "2026-11-06_ruta1_pipe_etiquetas.csv"
    assert salida.read_text(encoding="utf-8").splitlines() == ["t_s,clase", "5.0,hueco", "15.0,resalto"]
