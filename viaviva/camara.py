"""Video en vivo: webcam del PC o cámara de un celular, grabado por partes dentro de la sesión abierta.

- **Webcam del PC:** la app se abre en http://localhost, que el navegador trata como seguro: la cámara funciona.
- **Celular (iPhone B):** Safari solo da la cámara en HTTPS. La app levanta un segundo servidor HTTPS (puerto 8443)
  con un certificado firmado por una autoridad local propia (`data/certificados/`). Para que el iPhone lo acepte sin
  avisos hay que instalar y activar esa autoridad una vez (`/ca.crt`; pasos en README_SALIDA.md). SIN PROBAR EN IPHONE.

El video se guarda en la carpeta de la sesión como `video_vivo_<id>.mp4|webm` y `video.json` queda con
`metodo = "en_vivo"` y `desfase_s` = segundo de la sesión en que empezó la grabación (reloj del PC; el celular corrige
su reloj contra /api/hora antes de empezar).
"""
from __future__ import annotations

import datetime as dt
import ipaddress
import re
import threading
import time
from pathlib import Path

from viaviva import config

CARPETA_CERT = config.RAIZ / "data" / "certificados"
PUERTO_HTTPS = 8443
MAX_PARTE = 32 * 1024 * 1024
MAX_CUADRO = 600 * 1024
_ID = re.compile(r"^[A-Za-z0-9_-]{4,40}$")
_candado = threading.Lock()


# ------------------------------------------------------------------------------------------------ certificados
def _clave():
    from cryptography.hazmat.primitives.asymmetric import rsa
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def autoridad(carpeta: Path = CARPETA_CERT):
    """Autoridad local de VÍA VIVA (se crea una vez y se reutiliza: el iPhone la instala una sola vez)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID
    carpeta.mkdir(parents=True, exist_ok=True)
    f_cert, f_clave = carpeta / "ca.crt", carpeta / "ca.key"
    if f_cert.exists() and f_clave.exists():
        return (x509.load_pem_x509_certificate(f_cert.read_bytes()),
                serialization.load_pem_private_key(f_clave.read_bytes(), password=None))
    clave = _clave()
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "VIA VIVA autoridad local"),
                        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "VIA VIVA (proyecto USTA Tunja)")])
    ahora = dt.datetime.now(dt.UTC)
    cert = (x509.CertificateBuilder().subject_name(nombre).issuer_name(nombre).public_key(clave.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(ahora - dt.timedelta(days=1))
            .not_valid_after(ahora + dt.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                                         content_commitment=False, key_encipherment=False, data_encipherment=False,
                                         key_agreement=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(clave.public_key()), critical=False)
            .sign(clave, hashes.SHA256()))
    f_clave.write_bytes(clave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                            serialization.NoEncryption()))
    f_cert.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert, clave


def certificado_servidor(ips: list[str], carpeta: Path = CARPETA_CERT) -> tuple[Path, Path]:
    """Certificado del servidor HTTPS para estas IP (se rehace en cada arranque: la IP del hotspot cambia)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    ca_cert, ca_clave = autoridad(carpeta)
    clave = _clave()
    nombres: list = [x509.DNSName("localhost")]
    for ip in dict.fromkeys(["127.0.0.1", *[i for i in ips if i]]):
        try:
            nombres.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            nombres.append(x509.DNSName(ip))
    ahora = dt.datetime.now(dt.UTC)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "VIA VIVA app local")]))
            .issuer_name(ca_cert.subject).public_key(clave.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(ahora - dt.timedelta(days=1))
            .not_valid_after(ahora + dt.timedelta(days=397))           # iOS rechaza servidores de > 825 días
            .add_extension(x509.SubjectAlternativeName(nombres), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_clave.public_key()), critical=False)
            .sign(ca_clave, hashes.SHA256()))
    f_cert, f_clave = carpeta / "servidor.crt", carpeta / "servidor.key"
    f_clave.write_bytes(clave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                            serialization.NoEncryption()))
    f_cert.write_bytes(cert.public_bytes(serialization.Encoding.PEM) + ca_cert.public_bytes(serialization.Encoding.PEM))
    return f_cert, f_clave


def ca_der(carpeta: Path = CARPETA_CERT) -> bytes:
    """La autoridad en DER (.crt): así la abre iOS como perfil para instalar."""
    from cryptography.hazmat.primitives import serialization
    cert, _ = autoridad(carpeta)
    return cert.public_bytes(serialization.Encoding.DER)


# ------------------------------------------------------------------------------------------------ video por partes
class Grabaciones:
    """Video en vivo que llega por partes (MediaRecorder) a la sesión abierta, más el último cuadro para la vista
    previa del celular en el PC."""

    def __init__(self):
        self.activas: dict[str, dict] = {}
        self.cuadro: tuple[bytes, float, str] | None = None     # (jpeg, hora, origen)

    @staticmethod
    def extension(tipo: str) -> str:
        return ".mp4" if "mp4" in (tipo or "") else ".webm"

    def parte(self, carpeta: Path, ident: str, n: int, datos: bytes, tipo: str, desfase_s: float | None,
              origen: str, inicio_epoch: float | None = None) -> dict:
        from viaviva import sesiones
        if not _ID.match(ident or ""):
            raise ValueError("identificador de video inválido")
        if len(datos) > MAX_PARTE:
            raise ValueError("parte de video demasiado grande")
        with _candado:
            g = self.activas.get(ident)
            if n == 0:
                if g is not None:
                    raise ValueError("ese video ya empezó")
                archivo = carpeta / f"video_vivo_{time.strftime('%Y%m%d_%H%M%S')}_{ident[:8]}{self.extension(tipo)}"
                g = {"carpeta": carpeta, "archivo": archivo, "n": -1, "bytes": 0, "desfase_s": desfase_s,
                     "inicio": inicio_epoch or time.time(), "origen": origen, "tipo": tipo}
                self.activas[ident] = g
            elif g is None or g["carpeta"] != carpeta:
                raise ValueError("ese video no empezó en esta sesión")
            if n != g["n"] + 1:
                raise ValueError(f"falta la parte {g['n'] + 1} del video")
            with open(g["archivo"], "ab") as f:
                f.write(datos)
            g["n"], g["bytes"] = n, g["bytes"] + len(datos)
        if n == 0:
            sesiones._guardar_video_info(carpeta, archivo=g["archivo"].name, metodo="en_vivo",
                                         desfase_s=round(desfase_s or 0.0, 3), codec=("h264" if "mp4" in tipo else
                                                                                       "vp8/vp9"),
                                         avisos=[], origen_video=origen, conversion=None, en_curso=True,
                                         original=None, cobertura_pct=None, duracion_s=None)
        return {"ok": True, "archivo": g["archivo"].name, "partes": n + 1, "bytes": g["bytes"]}

    def fin(self, ident: str) -> dict:
        from viaviva import sesiones
        with _candado:
            g = self.activas.pop(ident, None)
        if g is None:
            raise ValueError("ese video no está grabando")
        duracion = round(time.time() - g["inicio"], 1)
        sesiones._guardar_video_info(g["carpeta"], en_curso=False, duracion_s=duracion)
        return {"ok": True, "archivo": g["archivo"].name, "duracion_s": duracion, "bytes": g["bytes"]}

    def poner_cuadro(self, jpeg: bytes, origen: str) -> None:
        if len(jpeg) > MAX_CUADRO or not jpeg.startswith(b"\xff\xd8"):
            raise ValueError("el cuadro debe ser un JPEG de menos de 600 KB")
        self.cuadro = (jpeg, time.time(), origen)

    def estado(self) -> dict:
        c = self.cuadro
        return {"grabando": [{"archivo": g["archivo"].name, "origen": g["origen"], "bytes": g["bytes"],
                              "partes": g["n"] + 1} for g in self.activas.values()],
                "cuadro_edad_s": None if c is None else round(time.time() - c[1], 1),
                "cuadro_origen": None if c is None else c[2]}
