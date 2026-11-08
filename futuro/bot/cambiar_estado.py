"""Cambia el estado de un reporte ciudadano (lo usa el operador; en la demo, el equipo).

Uso (desde via-viva/):
  bot\\.venv\\Scripts\\python bot\\cambiar_estado.py 12 confirmado
  bot\\.venv\\Scripts\\python bot\\cambiar_estado.py --listar
Estados: nuevo, confirmado, en_reparacion, reparado, descartado.
El ciudadano lo ve con /estado 12 (el bot no guarda su id, así que no puede avisarle solo).
"""
import argparse

import reportes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("id_reporte", nargs="?", type=int)
    ap.add_argument("estado", nargs="?", choices=reportes.ESTADOS)
    ap.add_argument("--listar", action="store_true", help="muestra los últimos 20 reportes")
    args = ap.parse_args()
    con = reportes.conectar()
    if args.listar or args.id_reporte is None:
        for f in con.execute("SELECT id_reporte, ts_utc, tipo, estado, round(lat, 5), round(lon, 5) FROM reportes "
                             "ORDER BY id_reporte DESC LIMIT 20"):
            print(*f, sep="  ")
        return
    if args.estado is None:
        ap.error("falta el estado")
    ok = reportes.cambiar_estado(args.id_reporte, args.estado, con)
    print(f"Reporte #{args.id_reporte} → {args.estado}" if ok else f"No existe el reporte #{args.id_reporte}")


if __name__ == "__main__":
    main()
