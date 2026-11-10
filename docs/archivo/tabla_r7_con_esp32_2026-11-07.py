"""R7 en la Raspberry Pi frente al ESP32 y el celular: arma la tabla con lo que YA está medido y deja [PENDIENTE]
en lo que falta. No inventa nada: cada celda sale de un archivo de data/logs/ (ignorado por Git).

    # 1. Con el servidor corriendo en la Pi (servicio via-viva-pi), el registro sale solo cada 10 s:
    #       data/logs/r7_pi.jsonl  (latencias del detector, lectura de la FIFO, ciclo I2C, % CPU, °C, RAM)
    # 2. Consumo con el tester USB entre el adaptador y la Pi (anotar a mano, en reposo y grabando):
    viaviva/.venv/bin/python viaviva/r7/tabla_r7.py consumo --estado reposo --ma 540 --v 5.08
    viaviva/.venv/bin/python viaviva/r7/tabla_r7.py consumo --estado grabando --ma 610 --v 5.07
    # 3. CNN de fotos en la Pi: viaviva/r7/benchmark_cnn.py  → data/logs/benchmark_cnn.jsonl
    # 4. Tabla (Markdown, para docs/experimentos.md y el texto del informe):
    viaviva/.venv/bin/python viaviva/r7/tabla_r7.py tabla
"""
from __future__ import annotations

import argparse
import json
import platform
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
LOGS = RAIZ / "data" / "logs"
P = "[PENDIENTE]"


def _lineas(nombre: str) -> list[dict]:
    ruta = LOGS / nombre
    if not ruta.exists():
        return []
    salida = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        try:
            salida.append(json.loads(linea))
        except json.JSONDecodeError:
            pass
    return salida


def _md(w: dict | None, unidad: str, dec: int = 1) -> str:
    if not w or not w.get("n"):
        return P
    return f"{w['media']:.{dec}f} ± {w['desv']:.{dec}f} {unidad} (n = {w['n']})"


def tabla() -> str:
    pi = [x for x in _lineas("r7_pi.jsonl") if "Raspberry" in (x.get("equipo") or "") and x.get("origen") == "nodo"]
    ult = pi[-1] if pi else {}
    lat = ult.get("latencias", {})
    cnn = [x for x in _lineas("benchmark_cnn.jsonl") if "pi" in (x.get("equipo") or "").lower()]
    cel = [x for x in _lineas("latencia_celular.jsonl") if "iPhone" in (x.get("navegador") or "")]
    consumo = {x["estado"]: x for x in _lineas("consumo_pi.jsonl")}
    filas = [
        ("Equipo", ult.get("equipo", P), "ESP32 WROOM-32 (240 MHz, 520 KB SRAM)", "iPhone 15 (navegador)"),
        ("Detector por umbrales, por muestra", _md(lat.get("detector_us"), "µs", 2), "E3/E4 del firmware: " + P, "—"),
        ("Vaciar la FIFO del ADXL345 (16 muestras)", _md(lat.get("lectura_fifo_ms"), "ms", 3),
         "DMA ping-pong (E1): " + P, "—"),
        ("INT1 → inicio de lectura (Linux, sin tiempo real)", _md(lat.get("irq_a_lectura_ms"), "ms", 3),
         "ISR → tarea: " + P, "—"),
        ("Ciclo I2C (MPU-6050 + VL53L0X + BH1750)", _md(lat.get("ciclo_i2c_ms"), "ms", 2), P, "—"),
        ("% CPU (toda la Pi, mientras graba)", _md(ult.get("cpu_resumen"), "%"), "ocio núcleo 1 (E1): " + P, "—"),
        ("Temperatura del SoC", _md(ult.get("temp_resumen"), "°C"), "—", "—"),
        ("RAM del proceso", f"{ult['memoria']['proceso_mb']} MB" if ult.get("memoria", {}).get("proceso_mb") else P,
         "RAM estática 66 348 B (pio run); heap libre: " + P, "—"),
        ("CNN de fotos int8 (MobileNetV2), por inferencia",
         f"{cnn[-1]['media_ms']:.1f} ± {cnn[-1]['desv_ms']:.1f} ms (n = {cnn[-1]['n']})" if cnn else P,
         "no cabe (activaciones ≥ 1 470 KB)",
         f"{cel[-1]['media_ms']:.1f} ± {cel[-1]['desv_ms']:.1f} ms (n = {cel[-1]['n']})" if cel else P),
    ]
    for estado in ("reposo", "grabando"):
        c = consumo.get(estado)
        filas.append((f"Consumo ({estado}, tester USB)", f"{c['ma']:.0f} mA × {c['v']:.2f} V = {c['ma'] * c['v'] / 1000:.2f} W"
                      if c else P, P, "—"))
    salida = ["| Medida | Raspberry Pi 4 | ESP32 (línea base) | Celular |", "|---|---|---|---|"]
    salida += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in filas]
    salida.append("")
    salida.append("Media ± desviación estándar con Welford; n = número de mediciones. Fuente: data/logs/ "
                  "(r7_pi.jsonl, benchmark_cnn.jsonl, latencia_celular.jsonl, consumo_pi.jsonl).")
    return "\n".join(salida)


def main():
    ap = argparse.ArgumentParser(description="Tabla de R7: Raspberry Pi 4 vs. ESP32 vs. celular")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tabla")
    c = sub.add_parser("consumo", help="anotar una lectura del tester USB")
    c.add_argument("--estado", choices=["reposo", "grabando"], required=True)
    c.add_argument("--ma", type=float, required=True)
    c.add_argument("--v", type=float, required=True)
    a = ap.parse_args()
    if a.cmd == "consumo":
        LOGS.mkdir(parents=True, exist_ok=True)
        fila = {"ts_utc": datetime.now(UTC).isoformat(timespec="seconds"), "equipo": platform.node(),
                "estado": a.estado, "ma": a.ma, "v": a.v}
        with open(LOGS / "consumo_pi.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(fila) + "\n")
        print(f"Anotado: {a.estado} {a.ma} mA × {a.v} V")
    else:
        print(tabla())


if __name__ == "__main__":
    main()
