# futuro/ — trabajo futuro (fuera del alcance de la entrega del 13-nov-2026)

Cambio de plan aprobado por el docente de Arquitectura el **3-nov-2026**. Nada de esta carpeta se compila, se monta ni
se reporta como resultado.

| Pieza | Por qué quedó para después | Qué hay |
|---|---|---|
| **ESP32-CAM (OV2640) + adaptador CP2102** | La evidencia fotográfica la toma el **celular** (mejor cámara, GPS y EXIF propios, sin cableado de 5 V ni picos de corriente). Ver `docs/protocolo_fotos.md` y `dataset/` | `nodo-camara/`: esqueleto PlatformIO (PING/FOTO por UART, difuminado total) tal como estaba el 2-nov |
| **Módulo láser de cuadrícula** (luz estructurada para medir la profundidad del hueco) | No se consigue a tiempo | Nada de código. La escala se obtiene hoy con la **tarjeta ArUco** de 10 × 10 cm (`docs/tarjeta_aruco.pdf`, `dataset/escala.py`) |
| **OBD2 (ELM327 Bluetooth, solo lectura)** | Opcional: velocidad y RPM del carro como respaldo del GPS | Nada de código. Si se retoma: solo lectura de PID estándar (`010D` velocidad), nunca escribir en la ECU |
| **Raspberry Pi 4 Model B** (`pi/`) | Opcional, bajo riesgo: servidor 24/7 del bot y del scraping, y benchmark de la CNN int8 para R7. La CNN de fotos **no cabe** en el ESP32 (activaciones ≥ 1 470 KB), así que el núcleo no cambia | `pi/README.md`, `pi/justificacion.md`, `pi/benchmark_cnn.py`, servicios systemd. Especificaciones pendientes |
