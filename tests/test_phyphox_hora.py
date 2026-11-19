"""Hora de phyphox ante pausas y «mediciones nuevas» (salida del 18-nov: ts_utc quedó 2 109 s adelantado y el buffer
se duplicó porque una pausa se tomó como medición nueva). Cliente falso: sin iPhone ni red."""
import threading
import time

from viaviva import fuente_phyphox as fp


class NucleoFalso:
    def __init__(self):
        self.base_epoch = 0.0
        self.ultimo_t = 0.0
        self.acc_t, self.avisos = [], []
        self.latencias = {"http_phyphox_ms": type("W", (), {"agregar": lambda s, x: None})()}

    def aviso(self, texto, tipo="aviso", **_):
        self.avisos.append((tipo, texto))

    def conexion(self, *_):
        pass

    def acc(self, filas, recibido=None):
        self.acc_t += [f[0] for f in filas]
        self.ultimo_t = filas[-1][0]

    def giro(self, *_):
        pass

    def gps(self, *_):
        pass


class ClienteFalso:
    """Entrega una lista de respuestas: cada una = (sesion, [t…]) del buffer de aceleración; respeta `desde`."""
    grupos = fp.GRUPOS
    url = "http://falso"

    def __init__(self, guion):
        self.guion, self.k, self.listo = guion, 0, threading.Event()

    def conectar(self):
        return {}

    def nuevos(self, desde):
        if self.k >= len(self.guion):
            self.listo.set()
            return {"status": {"session": self.guion[-1][0]}, "buffer": {}}
        sesion, ts = self.guion[self.k]
        self.k += 1
        ts = [t for t in ts if t > desde["acc"]]
        buf = {"acc_time": {"buffer": ts}, **{c: {"buffer": [0.0] * len(ts)} for c in ("accX", "accY", "accZ")}}
        return {"status": {"session": sesion, "measuring": True}, "buffer": buf}


def _correr(guion):
    n, cli = NucleoFalso(), ClienteFalso(guion)
    f = fp.FuentePhyphox(cliente=cli, intervalo_s=0.0)
    f.arrancar(n)
    assert cli.listo.wait(5)
    f.cerrar()
    return n, f


def test_pausa_tomada_como_medicion_nueva_no_duplica_ni_adelanta_la_hora():
    t = [round(i * 0.01, 2) for i in range(1, 60001)]            # 600 s de buffer
    guion = [("A", t[:50000]), ("B", t), ("B", t)]               # la sesión de phyphox «cambia» pero el buffer sigue
    n, f = _correr(guion)
    assert n.acc_t == t                                          # sin repetir lo ya recibido
    assert f.partes == 1
    assert any("misma medición" in x for _, x in n.avisos)
    # el buffer avanzó 100 s en un instante (como tras una pausa): la hora se re-ancla al reloj del PC
    assert abs(n.base_epoch - (time.time() - 600)) < 5
    assert any(tipo == "hora" for tipo, _ in n.avisos)


def test_medicion_nueva_de_verdad_sigue_el_tiempo():
    viejo = [round(i * 0.01, 2) for i in range(1, 30001)]        # 300 s
    nuevo = [round(i * 0.01, 2) for i in range(1, 101)]          # la medición nueva lleva 1 s
    n, f = _correr([("A", viejo), ("B", nuevo), ("B", nuevo)])
    assert f.partes == 2 and len(n.acc_t) == 30100 and n.acc_t[30000] > 300
    # t = 0 de phyphox en la hora del PC: el último dato (t ≈ 301 s de la sesión) es «ahora»
    assert abs(n.base_epoch + n.ultimo_t - time.time()) < 5
    assert not any("misma medición" in x for _, x in n.avisos)
