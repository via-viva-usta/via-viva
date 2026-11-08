"""Usuarios y roles del aplicativo. Las contraseñas las escribe cada persona en la consola de la Pi (getpass):
nunca pasan por el chat, por Git ni por la nube; en la base solo queda el hash PBKDF2-SHA256.

| Rol       | Quiénes                          | Puede                                                              |
|-----------|----------------------------------|--------------------------------------------------------------------|
| editor    | el equipo (4)                    | captura (grabar, etiquetar, apagar), cambiar estados, importar CSV |
| alcaldia  | Secretaría de Infraestructura    | ver el tablero y exportar (solo lectura)                           |
| docente   | docentes del Proyecto Integrador | ver el tablero y exportar (solo lectura)                           |

Sin ningún usuario creado, el aplicativo solo responde a la misma máquina (127.0.0.1) como editor: sirve para la
demo en el PC y para la instalación. En la red WiFi pide entrar.

    python -m pi.usuarios crear andres --rol editor --nombre "Andrés Cárdenas"
    python -m pi.usuarios listar
    python -m pi.usuarios desactivar docente1
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from pi.almacen import conectar

ROLES = ("editor", "alcaldia", "docente")
ITERACIONES = 200_000
DURACION_SESION = timedelta(days=30)        # el celular del carro no debe pedir clave cada salida
MAX_INTENTOS, VENTANA_INTENTOS_S = 5, 300


def _ahora():
    return datetime.now(timezone.utc)


def hash_clave(clave: str, sal: str | None = None, iteraciones: int = ITERACIONES) -> str:
    sal = sal or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), bytes.fromhex(sal), iteraciones).hex()
    return f"pbkdf2_sha256${iteraciones}${sal}${h}"


def verificar_clave(clave: str, guardado: str) -> bool:
    try:
        _, it, sal, h = guardado.split("$")
        return hmac.compare_digest(hash_clave(clave, sal, int(it)).split("$")[3], h)
    except (ValueError, IndexError):
        return False


def crear(con, usuario: str, clave: str, rol: str, nombre: str = "") -> None:
    usuario = usuario.strip().lower()
    if rol not in ROLES:
        raise ValueError(f"rol inválido: {rol} (use {', '.join(ROLES)})")
    if not usuario.isascii() or not usuario.replace("_", "").replace(".", "").isalnum():
        raise ValueError("usuario: solo letras, números, punto y guion bajo")
    if len(clave) < 10:
        raise ValueError("la contraseña debe tener al menos 10 caracteres")
    con.execute("INSERT INTO usuarios (usuario, nombre, rol, hash_clave, creado) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (usuario) DO UPDATE SET nombre = excluded.nombre, rol = excluded.rol, "
                "hash_clave = excluded.hash_clave, activo = 1",
                (usuario, nombre, rol, hash_clave(clave), _ahora().strftime("%Y-%m-%dT%H:%M:%SZ")))
    con.execute("DELETE FROM sesiones WHERE usuario = ?", (usuario,))      # cambiar la clave cierra sus sesiones
    con.commit()


def hay_usuarios(con) -> bool:
    return con.execute("SELECT 1 FROM usuarios WHERE activo = 1 LIMIT 1").fetchone() is not None


class Sesiones:
    """Inicio de sesión con límite de intentos por IP (5 en 5 min) y tokens aleatorios en cookie HttpOnly."""

    def __init__(self):
        self._intentos: dict[str, list[float]] = {}

    def bloqueada(self, ip: str) -> bool:
        ahora = time.monotonic()
        lista = [t for t in self._intentos.get(ip, []) if ahora - t < VENTANA_INTENTOS_S]
        self._intentos[ip] = lista
        return len(lista) >= MAX_INTENTOS

    def entrar(self, con, usuario: str, clave: str, ip: str) -> tuple[str, dict] | None:
        if self.bloqueada(ip):
            raise PermissionError("demasiados intentos: espere 5 minutos")
        f = con.execute("SELECT usuario, nombre, rol, hash_clave FROM usuarios WHERE usuario = ? AND activo = 1",
                        ((usuario or "").strip().lower(),)).fetchone()
        if f is None or not verificar_clave(clave or "", f[3]):
            if f is None:
                hash_clave(clave or "", "00" * 16)          # mismo tiempo de respuesta exista o no el usuario
            self._intentos.setdefault(ip, []).append(time.monotonic())
            return None
        token = secrets.token_urlsafe(32)
        con.execute("DELETE FROM sesiones WHERE expira < ?", (_ahora().strftime("%Y-%m-%dT%H:%M:%SZ"),))
        con.execute("INSERT INTO sesiones (token_sha256, usuario, expira) VALUES (?, ?, ?)",
                    (hashlib.sha256(token.encode()).hexdigest(), f[0],
                     (_ahora() + DURACION_SESION).strftime("%Y-%m-%dT%H:%M:%SZ")))
        con.commit()
        self._intentos.pop(ip, None)
        return token, {"usuario": f[0], "nombre": f[1], "rol": f[2]}

    @staticmethod
    def quien(con, token: str | None) -> dict | None:
        if not token:
            return None
        f = con.execute("SELECT u.usuario, u.nombre, u.rol FROM sesiones s JOIN usuarios u USING (usuario) "
                        "WHERE s.token_sha256 = ? AND s.expira > ? AND u.activo = 1",
                        (hashlib.sha256(token.encode()).hexdigest(),
                         _ahora().strftime("%Y-%m-%dT%H:%M:%SZ"))).fetchone()
        return {"usuario": f[0], "nombre": f[1], "rol": f[2]} if f else None

    @staticmethod
    def salir(con, token: str | None) -> None:
        if token:
            con.execute("DELETE FROM sesiones WHERE token_sha256 = ?", (hashlib.sha256(token.encode()).hexdigest(),))
            con.commit()


def main():
    ap = argparse.ArgumentParser(description="Usuarios del aplicativo VÍA VIVA (la contraseña se escribe aquí, oculta)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("crear", help="crear o cambiar la contraseña de un usuario")
    c.add_argument("usuario")
    c.add_argument("--rol", choices=ROLES, required=True)
    c.add_argument("--nombre", default="")
    sub.add_parser("listar")
    d = sub.add_parser("desactivar")
    d.add_argument("usuario")
    a = ap.parse_args()
    con = conectar()
    if a.cmd == "crear":
        clave = getpass.getpass(f"Contraseña para {a.usuario} (mín. 10 caracteres, no se muestra): ")
        if clave != getpass.getpass("Repítala: "):
            raise SystemExit("No coinciden; no se guardó nada.")
        crear(con, a.usuario, clave, a.rol, a.nombre)
        print(f"Listo: {a.usuario} ({a.rol}).")
    elif a.cmd == "listar":
        for u, n, r, act in con.execute("SELECT usuario, nombre, rol, activo FROM usuarios ORDER BY rol, usuario"):
            print(f"{u:16} {r:9} {'activo' if act else 'inactivo':9} {n or ''}")
    else:
        con.execute("UPDATE usuarios SET activo = 0 WHERE usuario = ?", (a.usuario,))
        con.execute("DELETE FROM sesiones WHERE usuario = ?", (a.usuario,))
        con.commit()
        print(f"{a.usuario} desactivado.")


if __name__ == "__main__":
    main()
