# Guion de la demo en vivo (5 min) y del video de respaldo (< 5 min)

Pitch en inglés (diseño, sección 13): problema → solución → demo → resultados → negocio. Este guion cubre la **demo**.
Regla: lo que no esté medido no se presenta como resultado. Si el modelo de riesgo de la demo es DEMO, el aviso rojo se
deja visible y se dice en voz alta.

## Antes de empezar (checklist, 30 min antes)

- [ ] Portátil cargado, con `.env` (token del bot) y la base actualizada.
- [ ] **Un comando** (PowerShell, en `via-viva\`): `.\demo\iniciar.ps1`. Levanta en orden el tablero Java, el mapa web
      (http://localhost:8080), el bot y la página del clasificador para el celular. Si la base real no tiene eventos ni
      reportes, usa sola la **base DEMO** (`data\via_viva_demo.db`, todo marcado DEMO; la real no se toca).
      Opciones: `-Demo` (forzar DEMO), `-SinBot`, `-SinCelular`, `-SinTablero`.
- [ ] iPhone en el mismo WiFi que el portátil, con la URL del clasificador abierta (la imprime la ventana de
      `preparar.py`). Si no abre: permitir Python en el Firewall de Windows (red privada).
- [ ] Nodo encendido con power bank; otro celular en la red `VIA-VIVA-NODO` y en http://192.168.4.1 (gráfica en vivo).
- [ ] Tarjeta ArUco y un par de fotos de Tunja (o una impresa) para clasificar en vivo.
- [ ] **Video de respaldo** en el escritorio por si algo falla (no se depende de la red del auditorio).

## Demo en vivo (5:00)

| Tiempo | Quién | Qué se muestra | Qué se dice (idea, en inglés) |
|---|---|---|---|
| 0:00–0:40 | Dany | Nodo en la mano; página del nodo con la **gráfica en vivo**; golpe sobre la mesa con **modo mesa** → evento | "An ESP32 reads the accelerometer through a FIFO and DMA; the threshold detector fires on the device, and only the event leaves the node." |
| 0:40–1:05 | Dany | Girar el nodo: *giro izquierda*; mostrar un umbral ajustado desde la página y **descargar el CSV** por WiFi | "The gyroscope separates maneuvers from potholes; thresholds are tuned from the phone and data is downloaded without removing the SD card." |
| 1:05–2:05 | Juan Diego | iPhone: **clasificador en el navegador** → foto de un hueco → clase, confianza y latencia en ms; luego la vista cenital con la **tarjeta ArUco** | "The phone is our edge device for images: the int8 network runs in the browser, offline. The ArUco card gives metric scale." |
| 2:05–2:45 | Juan Felipe | Bot: foto + ubicación → "Parece un hueco (N %)" → "Reporte #N" | "Citizens report where the vehicle does not go; the CNN suggests a class, a human confirms it." |
| 2:45–3:10 | Andrés | `bot\cambiar_estado.py N confirmado` y `/estado N` | "The authority updates the status; the citizen sees it." |
| 3:10–4:10 | Andrés | Tablero Java: pestaña **Reportes y eventos** (heap: severidad × tránsito × reincidencia), ranking de riesgo, corredor (BFS) | "A hash table, a binary heap and BFS rank what to repair first." |
| 4:10–5:00 | Juan Diego | Mapa web; matriz de confusión y **Grad-CAM** del modelo de fotos (`dataset\salidas\...`) | "Validated by neighborhood and by site: [real results]. Grad-CAM shows where the network looked." |

Con la base DEMO o un modelo SINTÉTICO, el aviso rojo queda visible y se dice en voz alta: "these are demo data; real
results are pending". Nunca se presentan números sintéticos como resultados.

## Si algo falla

| Falla | Plan B inmediato |
|---|---|
| El nodo no arranca o no hay Wi-Fi | Mostrar el monitor serie por USB en el portátil, o pasar al video |
| El bot no responde (sin internet) | Mostrar un reporte ya hecho con `/mis_reportes` en captura, o el video |
| El mapa no carga teselas (sin internet) | El tablero Java funciona sin internet |
| Cualquier otra | Video de respaldo desde el minuto correspondiente |

## Video de respaldo (< 5 min, 1080p, subtítulos en inglés)

| # | Duración | Toma |
|---|---|---|
| 1 | 0:20 | Calle de Tunja con huecos (grabar con permiso; sin placas ni rostros legibles) |
| 2 | 0:30 | Montaje del nodo en el carro: caja, GPS al parabrisas, sensor de ambiente fuera de la caja |
| 3 | 0:50 | Recorrido a ≤ 30 km/h (copiloto filma la pantalla del celular con la página del nodo y los eventos) |
| 4 | 0:30 | Paso por un hueco: evento en la página del nodo; luego, en el andén, las 4 fotos del celular con la tarjeta ArUco |
| 5 | 0:40 | Reporte con el bot de principio a fin |
| 6 | 0:50 | Tablero Java: ranking, corredor, zonas |
| 7 | 0:40 | Mapa web con la capa de riesgo y la fuente de las etiquetas |
| 8 | 0:30 | Cierre: resultados medidos (solo los reales) y próximos pasos |

Grabar las tomas 3–4 **solo con conductor + copiloto**, el conductor no toca nada. Pantallas con OBS Studio.
Revisar que en ningún cuadro se vea el token del bot ni el contenido de `.env`.
