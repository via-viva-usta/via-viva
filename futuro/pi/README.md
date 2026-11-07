# futuro/pi — Raspberry Pi 4 Model B (bajo riesgo, opcional)

**El núcleo del nodo sigue siendo el ESP32** (nada del firmware cambia). La Pi 4 solo se usaría para dos cosas que hoy
hace el portátil de Andrés:

1. **Servidor 24/7** del bot de Telegram y del scraping diario (IDEAM + noticias), sin depender de que el PC esté prendido.
2. **Benchmark** de la misma CNN int8 de fotos en Pi 4 vs. ESP32 vs. celular, para la comparación obligatoria de
   Arquitectura (R7). Justificación de por qué no es sobredimensionar: [`justificacion.md`](justificacion.md).

**Especificaciones pendientes** (anotar cuando se consiga la placa): RAM (2/4/8 GB) · cámara (no se usa por ahora) ·
fuente (5 V / 3 A USB-C oficial) · microSD (≥ 16 GB clase A1).

## Instalar (Raspberry Pi OS Lite 64-bit, Bookworm)

```bash
sudo apt update && sudo apt install -y git python3-venv
git clone https://github.com/via-viva-usta/via-viva.git ~/via-viva && cd ~/via-viva
bash futuro/pi/instalar.sh          # venvs del bot y del ETL + servicios systemd
nano ~/via-viva/.env                # token del bot y BOT_SAL_HASH (copiarlos a mano: nunca por chat ni Git)
sudo systemctl start via-viva-bot   # y revisar: journalctl -u via-viva-bot -f
```

| Archivo | Qué hace |
|---|---|
| `instalar.sh` | Crea `bot/.venv` y `etl/.venv` (con `entornos/*.txt` si hay ruedas para ARM; si no, los `requirements.txt`) y copia los servicios |
| `via-viva-bot.service` | Bot de Telegram siempre encendido (se reinicia solo si se cae) |
| `via-viva-scraping.service` + `.timer` | Scraping diario (`etl.scraping.diario`) a las 06:30, y al arrancar si se perdió la hora |
| `benchmark_cnn.py` | Latencia (100 inferencias, media ± desviación), RAM, memoria de activaciones, ¿cabe en el ESP32?, energía por inferencia |

La base SQLite (`data/via_viva.db`) se copia del PC (`scp`) o se reconstruye con `etl` (sin `db/reconstruir.ps1`, que
es de PowerShell). Los datos siguen fuera de Git.

## Benchmark (R7)

```bash
~/via-viva/bot/.venv/bin/python futuro/pi/benchmark_cnn.py --equipo "Pi 4 (RAM ?)" --corriente-ma <tester> --voltaje 5.1
```

Copiar al PC `dataset/salidas/<versión>/` antes (el modelo no está en Git). Resultado: `data/logs/benchmark_cnn.jsonl`.

| Equipo | Modelo | Latencia (media ± desv., n = 100) | Activaciones | ¿Cabe en el ESP32? | Fuente |
|---|---|---|---|---|---|
| PC de Andrés (control) | MobileNetV2 int8 (SINTÉTICO) | 5,16 ± 0,34 ms (LiteRT + XNNPACK) | ≥ 1 470 KB | **No** (SRAM libre ~300 KB; modelo 2,6 MB > ~1 MB de flash libre) | `benchmark_cnn.py`, 7-nov |
| PC de Andrés (control) | MobileNetV3-Small int8 (SINTÉTICO) | 171,41 ± 59,24 ms (sin XNNPACK) | ≥ 392 KB | **No** (> 300 KB; 1,2 MB > ~1 MB de flash libre) | `benchmark_cnn.py`, 7-nov |
| Chromium del PC (control) | MobileNetV2 int8 | 10,73 ± 0,26 ms | — | — | `web/clasificador`, 7-nov |
| **Raspberry Pi 4** | MobileNetV2 int8 | [PENDIENTE] | — | — | este script en la Pi |
| **iPhone 15** (Safari) | MobileNetV2 int8 | [PENDIENTE] | — | — | `web/clasificador` |
| **ESP32** | Red 1D int8 del nodo (788 parámetros, 872 B) | [PENDIENTE: E3 en la placa] | (cabe: es la red del nodo) | Sí | `exp_NNN.csv` |

La latencia no depende de que el modelo sea sintético (misma arquitectura y tamaño); la exactitud sí, y no se reporta.
