"""El bot guarda la sugerencia de la CNN junto al reporte (columnas nuevas migradas solas). Base temporal."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "futuro" / "bot"))   # bot pospuesto el 7-nov


def test_guardar_reporte_con_sugerencia(tmp_path):
    import reportes
    from db.acceso import conectar
    con = conectar(f"sqlite:///{(tmp_path / 'prueba.db').as_posix()}")
    s = {"clase": "hueco", "confianza": 0.87, "version": "20261105-0752-SINTETICO", "sintetico": True}
    n = reportes.guardar_reporte("h", "hueco", 5.5353, -73.3678, "data/fotos_bot/x.jpg", None, con=con, sugerencia=s)
    fila = con.execute("SELECT clase_sugerida, confianza_sugerida, modelo_sugerencia FROM reportes WHERE id_reporte=?",
                       (n,)).fetchone()
    assert tuple(fila) == ("hueco", 0.87, "20261105-0752-SINTETICO")
    n2 = reportes.guardar_reporte("h", "otro", 5.5353, -73.3678, con=con)          # sin modelo: queda vacío
    assert con.execute("SELECT clase_sugerida FROM reportes WHERE id_reporte=?", (n2,)).fetchone()[0] is None


def test_version_sintetica_queda_marcada(tmp_path):
    import reportes
    from db.acceso import conectar
    con = conectar(f"sqlite:///{(tmp_path / 'p.db').as_posix()}")
    n = reportes.guardar_reporte("h", "hueco", 5.5353, -73.3678, con=con,
                                 sugerencia={"clase": "hueco", "confianza": 0.5, "version": "20261105", "sintetico": True})
    assert con.execute("SELECT modelo_sugerencia FROM reportes WHERE id_reporte=?", (n,)).fetchone()[0].endswith("SINTETICO")
