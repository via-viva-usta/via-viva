"""Exportables del tablero (PDF top-10 con mapa, CSV, Excel de 3 hojas) e importación de reparaciones por CSV.

Todo se genera en la Pi, sin internet: el mapa del PDF se dibuja con las geometrías de OSM que ya están en la base.
Los datos DEMO/SINTÉTICOS salen marcados en rojo en cada archivo.
"""
from __future__ import annotations

import csv
import io
import math
from datetime import UTC, date, datetime, timedelta, timezone

from viaviva import almacen

COL_HUECOS = [("id_hueco", "Id hueco"), ("estado", "Estado"), ("clase", "Clase"), ("n_detecciones", "Detecciones"),
              ("lat", "Latitud"), ("lon", "Longitud"), ("id_tramo", "Id tramo"), ("nombre_via", "Calle"),
              ("barrio", "Barrio"), ("tipo_via", "Tipo de vía"), ("primera_ts", "Primera detección (UTC)"),
              ("ultima_ts", "Última detección (UTC)"), ("ts_estado", "Cambio de estado (UTC)"),
              ("usuario_estado", "Cambiado por"), ("nota", "Nota"), ("simulado", "Simulado/DEMO")]
COL_RIESGO = [("rango", "Rango"), ("id_tramo", "Id tramo"), ("nombre", "Calle"), ("barrio", "Barrio"),
              ("tipo_via", "Tipo de vía"), ("longitud_m", "Longitud (m)"), ("probabilidad", "Probabilidad"),
              ("reportado", "Con huecos conocidos")]
COLORES_ESTADO = {"detectado": "#d6402b", "verificado": "#9a6700", "reparado": "#1a7f37", "descartado": "#8c959f"}


def _texto(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "sí" if v else "no"
    return v


# ------------------------------------------------------------------------------------------------ CSV
def csv_tabla(filas: list[dict], columnas) -> bytes:
    """CSV con BOM UTF-8 (Excel abre bien las tildes) y separador coma."""
    s = io.StringIO()
    w = csv.writer(s)
    w.writerow([t for _, t in columnas])
    for f in filas:
        w.writerow([_texto(f.get(c)) for c, _ in columnas])
    return ("﻿" + s.getvalue()).encode("utf-8")


def plantilla_reparaciones() -> bytes:
    return ("﻿id_hueco,estado,fecha,nota\n"
            "12,reparado,2026-11-20,Parcheo cuadrilla 3 (EJEMPLO: borre esta fila)\n").encode()


# ------------------------------------------------------------------------------------------------ Excel
def excel(huecos: list[dict], riesgo: dict, peligros: dict, resumen: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    negrita, blanco = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F6FEB")
    rojo = Font(bold=True, color="CF222E")

    def hoja(ws, columnas, filas, anchos=None):
        ws.append([t for _, t in columnas])
        for c in ws[1]:
            c.font, c.fill, c.alignment = negrita, blanco, Alignment(vertical="center", wrap_text=True)
        for f in filas:
            ws.append([_texto(f.get(c)) for c, _ in columnas])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for i, (c, t) in enumerate(columnas, start=1):
            ws.column_dimensions[get_column_letter(i)].width = (anchos or {}).get(c, max(10, min(40, len(t) + 4)))

    ws = wb.active
    ws.title = "Huecos"
    hoja(ws, COL_HUECOS, huecos, {"nombre_via": 28, "nota": 40, "barrio": 20})
    for fila in ws.iter_rows(min_row=2, min_col=5, max_col=6):
        for c in fila:
            c.number_format = "0.000000"

    ws = wb.create_sheet("Riesgo por tramo")
    tramos = sorted(riesgo.get("tramos", []), key=lambda x: -x["probabilidad"])
    hoja(ws, COL_RIESGO, tramos, {"nombre": 30, "barrio": 20})
    for fila in ws.iter_rows(min_row=2, min_col=7, max_col=7):
        for c in fila:
            c.number_format = "0.0%"

    ws = wb.create_sheet("Top-10 y resumen")
    c = riesgo.get("corrida") or {}
    ws.append(["VÍA VIVA · tablero para la Alcaldía de Tunja"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append(["Generado", datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")])
    ws.append(["Modelo de riesgo", f"{c.get('modelo', '—')} · {c.get('version', '—')} · {c.get('fecha', '—')}"])
    ws.append(["Etiquetas del modelo", c.get("fuente") or "—"])
    if c.get("demo"):
        ws.append(["AVISO", "Corrida DEMO/SINTÉTICA: no es un resultado."])
        ws.cell(ws.max_row, 1).font = ws.cell(ws.max_row, 2).font = rojo
    ws.append([])
    ws.append(["Huecos por estado"] + list(resumen))
    ws.append([""] + list(resumen.values()))
    ws.append(["Peligros abiertos", peligros.get("abiertos", 0)])
    ws.append([])
    inicio = ws.max_row + 1
    ws.append(["Rango", "Calle", "Barrio", "Tipo de vía", "Probabilidad", "Con huecos conocidos"])
    for celda in ws[inicio]:
        celda.font, celda.fill = negrita, blanco
    for i, t in enumerate(riesgo.get("top10", []), start=1):
        ws.append([i, t.get("nombre") or f"tramo {t['id_tramo']}", t.get("barrio") or "", t.get("tipo_via") or "",
                   t["probabilidad"], "sí" if t.get("reportado") else "no"])
        ws.cell(ws.max_row, 5).number_format = "0.0%"
    for col, ancho in zip("ABCDEF", (22, 32, 20, 14, 13, 20)):
        ws.column_dimensions[col].width = ancho
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


# ------------------------------------------------------------------------------------------------ PDF
def pdf_top10(riesgo: dict, huecos: list[dict], resumen: dict, calles) -> bytes:
    """Una hoja A4: mapa de Tunja (tramos en gris, top-10 numerado, huecos por estado) + tabla del top-10."""
    from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    est = getSampleStyleSheet()
    c = riesgo.get("corrida") or {}
    top = riesgo.get("top10", [])
    ids_top = {t["id_tramo"]: i for i, t in enumerate(top, start=1)}
    ancho, alto = 18 * cm, 12.5 * cm
    d = Drawing(ancho, alto)
    d.add(Rect(0, 0, ancho, alto, fillColor=colors.HexColor("#f4f5f7"), strokeColor=colors.HexColor("#d9dee3")))
    geoms = [(t, (calles.info.obtener(t) or {}).get("puntos")) for t in (x["id_tramo"] for x in riesgo.get("tramos", []))]
    geoms = [(t, p) for t, p in geoms if p]
    if not geoms:
        geoms = [(k, v["puntos"]) for k, v in calles.info.items()]
    puntos = [p for _, ps in geoms for p in ps] + [[h["lat"], h["lon"]] for h in huecos]
    if puntos:
        la = sorted(p[0] for p in puntos)
        lo = sorted(p[1] for p in puntos)
        # recorte al 1–99 % para que un tramo suelto lejano no achique la ciudad
        la0, la1 = la[len(la) // 100], la[-1 - len(la) // 100]
        lo0, lo1 = lo[len(lo) // 100], lo[-1 - len(lo) // 100]
        k = math.cos(math.radians((la0 + la1) / 2))
        esc = min((ancho - 20) / max((lo1 - lo0) * k, 1e-6), (alto - 20) / max(la1 - la0, 1e-6))
        ox = (ancho - (lo1 - lo0) * k * esc) / 2
        oy = (alto - (la1 - la0) * esc) / 2
        xy = lambda lat, lon: (ox + (lon - lo0) * k * esc, oy + (lat - la0) * esc)
        dentro = lambda x, y: 0 <= x <= ancho and 0 <= y <= alto
        for t, ps in geoms:
            if t in ids_top:
                continue
            pts = [v for p in ps for v in xy(*p)]
            if all(dentro(pts[i], pts[i + 1]) for i in range(0, len(pts), 2)):
                d.add(PolyLine(pts, strokeColor=colors.HexColor("#c4cad0"), strokeWidth=0.35))
        for h in huecos:
            x, y = xy(h["lat"], h["lon"])
            if dentro(x, y):
                d.add(Circle(x, y, 2.2, fillColor=colors.HexColor(COLORES_ESTADO[h["estado"]]),
                             strokeColor=colors.white, strokeWidth=0.4))
        for t, ps in geoms:
            if t in ids_top:
                pts = [v for p in ps for v in xy(*p)]
                d.add(PolyLine(pts, strokeColor=colors.HexColor("#8f1d21"), strokeWidth=2.6))
                mx, my = xy(*ps[len(ps) // 2])
                d.add(Circle(mx, my + 7, 6, fillColor=colors.HexColor("#8f1d21"), strokeColor=colors.white))
                d.add(String(mx, my + 4.6, str(ids_top[t]), fontSize=7, fillColor=colors.white,
                             textAnchor="middle", fontName="Helvetica-Bold"))
        y = alto - 12
        for nombre, color in COLORES_ESTADO.items():
            d.add(Circle(10, y + 2.5, 3, fillColor=colors.HexColor(color), strokeColor=colors.white))
            d.add(String(17, y, f"hueco {nombre} ({resumen.get(nombre, 0)})", fontSize=7))
            y -= 10
        d.add(Line(8, y + 2, 16, y + 2, strokeColor=colors.HexColor("#8f1d21"), strokeWidth=2.6))
        d.add(String(19, y, "top-10 de riesgo", fontSize=7))

    historia = [Paragraph("VÍA VIVA · Top-10 de tramos con mayor riesgo de huecos", est["Title"]),
                Paragraph(f"Tunja · generado {datetime.now().astimezone():%Y-%m-%d %H:%M} · modelo "
                          f"{c.get('modelo', '—')} {c.get('version', '—')} ({c.get('fecha', '—')}) · etiquetas: "
                          f"{c.get('fuente') or '—'}", est["Normal"])]
    if c.get("demo"):
        historia.append(Paragraph('<font color="#cf222e"><b>Corrida DEMO/SINTÉTICA: sirve para probar el flujo, no es '
                                  'un resultado.</b></font>', est["Normal"]))
    historia += [Spacer(1, 6), d, Spacer(1, 8)]
    datos = [["#", "Calle", "Barrio", "Tipo", "Long. (m)", "Prob.", "Abiertos", "Conocido"]]
    abiertos = {}
    for h in huecos:
        if h["estado"] in ("detectado", "verificado") and h["id_tramo"] is not None:
            abiertos[h["id_tramo"]] = abiertos.get(h["id_tramo"], 0) + 1
    for i, t in enumerate(top, start=1):
        datos.append([i, (t.get("nombre") or f"tramo {t['id_tramo']}")[:34], (t.get("barrio") or "—")[:22],
                      t.get("tipo_via") or "—", f"{t.get('longitud_m') or 0:.0f}", f"{t['probabilidad'] * 100:.0f} %",
                      abiertos.get(t["id_tramo"], 0), "sí" if t.get("reportado") else "no"])
    if len(datos) == 1:
        datos.append(["", "Sin corridas del modelo de riesgo en esta base", "", "", "", "", "", ""])
    tabla = Table(datos, repeatRows=1, colWidths=[0.7 * cm, 5.4 * cm, 3.4 * cm, 2 * cm, 1.6 * cm, 1.3 * cm, 2 * cm, 1.6 * cm])
    tabla.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f6feb")),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8),
                               ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f5f7")]),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d9dee3"))]))
    historia += [tabla, Spacer(1, 6),
                 Paragraph("Probabilidad = modelo predictivo por tramo (risk_model). Huecos = detecciones del nodo "
                           "agrupadas a 10 m o menos; estados del tablero (detectado, verificado, reparado, descartado). "
                           "Calles: © OpenStreetMap (ODbL).", est["Italic"])]
    salida = io.BytesIO()
    SimpleDocTemplate(salida, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.2 * cm,
                      bottomMargin=1.2 * cm, title="VÍA VIVA top-10", author="VÍA VIVA").build(historia)
    return salida.getvalue()


# ------------------------------------------------------------------------------------------------ importar
ALIAS = {"id_hueco": "id_hueco", "id": "id_hueco", "hueco": "id_hueco", "estado": "estado", "fecha": "fecha",
         "fecha_reparacion": "fecha", "fecha reparación": "fecha", "fecha reparacion": "fecha", "nota": "nota",
         "observacion": "nota", "observación": "nota", "notas": "nota"}
MAX_FILAS, MAX_BYTES = 5000, 1_000_000


def _fecha(texto: str) -> date:
    texto = texto.strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            pass
    raise ValueError("fecha inválida (use AAAA-MM-DD o DD/MM/AAAA)")


def importar_reparaciones(con, datos: bytes, usuario: str, aplicar: bool = False) -> dict:
    """Valida TODO el archivo; solo si no hay errores (y aplicar=True) cambia los estados, en una transacción.
    Columnas: id_hueco (obligatoria), estado (reparado si falta), fecha (obligatoria si es reparado), nota."""
    errores, cambios = [], []

    def error(fila, columna, mensaje):
        errores.append({"fila": fila, "columna": columna, "mensaje": mensaje})

    if len(datos) > MAX_BYTES:
        return {"filas": 0, "errores": [{"fila": 0, "columna": "", "mensaje": "archivo de más de 1 MB"}],
                "cambios": [], "aplicado": False}
    try:
        texto = datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = datos.decode("latin-1")             # Excel en Windows a veces guarda en ANSI
    try:
        dialecto = csv.Sniffer().sniff(texto[:2048], delimiters=",;\t")
    except csv.Error:
        dialecto = csv.excel
    lector = csv.reader(io.StringIO(texto), dialecto)
    encabezado = next(lector, None)
    if not encabezado:
        return {"filas": 0, "errores": [{"fila": 1, "columna": "", "mensaje": "archivo vacío"}], "cambios": [],
                "aplicado": False}
    cols = [ALIAS.get(c.strip().lower()) for c in encabezado]
    if "id_hueco" not in cols:
        error(1, "id_hueco", "falta la columna id_hueco (descargue la plantilla)")
    desconocidas = [c for c, a in zip(encabezado, cols) if a is None and c.strip()]
    if desconocidas:
        error(1, ", ".join(desconocidas), "columnas desconocidas (use id_hueco, estado, fecha, nota)")
    vistos: dict[int, int] = {}
    hoy = datetime.now().date()
    n = 0
    if not errores:
        for n, fila in enumerate(lector, start=2):
            if n - 1 > MAX_FILAS:
                error(n, "", f"más de {MAX_FILAS} filas")
                break
            if not any(x.strip() for x in fila):
                continue
            r = {c: (fila[i].strip() if i < len(fila) else "") for i, c in enumerate(cols) if c}
            try:
                idh = int(r.get("id_hueco", ""))
            except ValueError:
                error(n, "id_hueco", f"no es un número: «{r.get('id_hueco', '')}»")
                continue
            if idh in vistos:
                error(n, "id_hueco", f"repetido (ya está en la fila {vistos[idh]})")
                continue
            vistos[idh] = n
            h = con.execute("SELECT estado, primera_ts FROM huecos WHERE id_hueco = ?", (idh,)).fetchone()
            if h is None:
                error(n, "id_hueco", f"el hueco {idh} no existe")
                continue
            estado = (r.get("estado") or "reparado").lower()
            if estado not in almacen.ESTADOS_HUECO:
                error(n, "estado", f"«{estado}» no es válido ({', '.join(almacen.ESTADOS_HUECO)})")
                continue
            ts = None
            if r.get("fecha"):
                try:
                    f = _fecha(r["fecha"])
                except ValueError as err:
                    error(n, "fecha", str(err))
                    continue
                if f > hoy:
                    error(n, "fecha", f"{f} está en el futuro")
                    continue
                if f < date.fromisoformat(h[1][:10]) - timedelta(days=1):
                    error(n, "fecha", f"{f} es anterior a la primera detección ({h[1][:10]})")
                    continue
                ts = datetime(f.year, f.month, f.day, 12, tzinfo=timezone(timedelta(hours=-5))) \
                    .astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            elif estado == "reparado":
                error(n, "fecha", "falta la fecha de la reparación")
                continue
            cambios.append({"fila": n, "id_hueco": idh, "antes": h[0], "despues": estado, "ts": ts,
                            "nota": r.get("nota") or None})
    aplicado = False
    if aplicar and not errores and cambios:
        try:
            for ch in cambios:
                almacen.cambiar_estado_hueco(con, ch["id_hueco"], ch["despues"], f"csv:{usuario}", origen="csv",
                                             nota=ch["nota"], ts=ch["ts"], confirmar=False)
            con.commit()
            aplicado = True
        except Exception:
            con.rollback()
            raise
    return {"filas": max(0, n - 1), "validas": len(cambios), "errores": errores, "cambios": cambios,
            "aplicado": aplicado}
