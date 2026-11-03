# Guion de la demo en vivo (5 min) y del video de respaldo (< 5 min)

Pitch en inglés (diseño, sección 13): problema → solución → demo → resultados → negocio. Este guion cubre la **demo**.
Regla: lo que no esté medido no se presenta como resultado. Si el modelo de riesgo de la demo es DEMO, el aviso rojo se
deja visible y se dice en voz alta.

## Antes de empezar (checklist, 30 min antes)

- [ ] Portátil cargado, con `.env` (token del bot) y la base actualizada (`db\reconstruir.ps1` ya corrido + recorridos).
- [ ] Bot corriendo: `bot\.venv\Scripts\python bot\bot.py` (ventana minimizada, sin mostrar `.env`).
- [ ] Mapa web: `etl\.venv\Scripts\python web\exportar.py` y `web\index.html` abierto (o la URL de Netlify si ya se publicó).
- [ ] Tablero Java abierto en NetBeans (o `java -jar dashboard-java\dist\TableroViaViva.jar`).
- [ ] Nodo encendido con power bank; celular de demo conectado a la red `VIA-VIVA-NODO` y en http://192.168.4.1.
- [ ] Un segundo celular con Telegram para reportar en vivo.
- [ ] **Video de respaldo** en el escritorio por si algo falla (no se depende de la red del auditorio).

## Demo en vivo (5:00)

| Tiempo | Quién | Qué se muestra | Qué se dice (idea, en inglés) |
|---|---|---|---|
| 0:00–0:30 | Andrés | Nodo en la mano (caja abierta) | "This is the node: an ESP32 reads the accelerometer through a FIFO and DMA, and classifies events on the device." |
| 0:30–1:30 | Dany | Golpear el nodo sobre la mesa con **modo mesa** activo; la página del celular muestra el último evento y la clase | "The threshold detector fires, the int8 network classifies, and only the event leaves the node — not the trajectory." |
| 1:30–2:00 | Dany | Girar el nodo sobre la mesa: aparece *giro izquierda* | "The gyroscope separates turns and hard braking from potholes." |
| 2:00–2:45 | Juan Felipe | Reportar un hueco con el bot: foto + ubicación + tipo → "Reporte #N" | "Citizens cover the streets the vehicle does not drive. We only store an anonymous hash." |
| 2:45–3:15 | Andrés | `bot\cambiar_estado.py N confirmado` y `/estado N` en el celular | "The authority updates the status; the citizen sees it." |
| 3:15–4:15 | Andrés | Tablero Java: ranking (heap), clic en un tramo (geohash), corredor (BFS), zonas de alto riesgo | "A hash table, a binary heap and BFS rank and group the segments to repair." |
| 4:15–5:00 | Juan Diego | Mapa web con el riesgo por tramo y la fuente de las etiquetas (Alcaldía o recorridos + bot) | "This is the public map. The risk model was validated by neighborhood: [AUC real]. In the field, the top-10 segments had [N] potholes vs [M] in random ones." |

Si el modelo de riesgo todavía es DEMO, el último paso dice: "this map uses synthetic labels; real results are pending".

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
| 2 | 0:30 | Montaje del nodo en el carro: caja, GPS al parabrisas, cámara |
| 3 | 0:50 | Recorrido a ≤ 30 km/h (copiloto filma la pantalla del celular con la página del nodo y los eventos) |
| 4 | 0:30 | Paso por un hueco: evento en la página + foto difuminada de la ESP32-CAM |
| 5 | 0:40 | Reporte con el bot de principio a fin |
| 6 | 0:50 | Tablero Java: ranking, corredor, zonas |
| 7 | 0:40 | Mapa web con la capa de riesgo y la fuente de las etiquetas |
| 8 | 0:30 | Cierre: resultados medidos (solo los reales) y próximos pasos |

Grabar las tomas 3–4 **solo con conductor + copiloto**, el conductor no toca nada. Pantallas con OBS Studio.
Revisar que en ningún cuadro se vea el token del bot ni el contenido de `.env`.
