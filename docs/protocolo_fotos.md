# Protocolo de fotos con el celular — dataset propio de VÍA VIVA

Cambio de plan del **3-nov-2026** (aprobado por el docente de Arquitectura): la evidencia visual la toma el **celular**
(dispositivo de borde para imágenes), no una ESP32-CAM. Con estas fotos se entrena el clasificador de imágenes
(`dataset/modelo.py`) y se mide el tamaño de los daños con la tarjeta ArUco (`dataset/escala.py`).
Entrega final: 13-nov. **Recolección: 4 al 9 de noviembre**; etiquetado 8–10 nov; modelo 10–11 nov.

## 1. Meta

- **≥ 500 fotos** en total y **≥ 50 por clase** (9 clases).
- Cada punto (sitio) da 4–5 fotos. El modelo se evalúa **por sitio** (las fotos de un mismo hueco nunca quedan a la vez
  en entrenamiento y en prueba), así que importa tener **muchos sitios distintos**: al menos **12 sitios por clase**.
- Variedad: distintos ángulos, luces, momentos del día, tipos de vía y climas (tablas abajo). El reporte
  `data/procesado/reporte_calidad.md` (lo genera `dataset.ingesta`) dice qué falta.

## 2. Clases

| # | Clase | Qué es | Severidad (solo daños) |
|---|---|---|---|
| 1 | `hueco` | Bache: falta material y hay cavidad | leve < 15 cm de ancho y < 3 cm de hondo · media 15–40 cm o 3–7 cm · alta > 40 cm o > 7 cm (la llanta cae) |
| 2 | `resalto` | Reductor de velocidad (policía acostado), pintado o no | — |
| 3 | `grieta` | Fisuras en el asfalto (sin cavidad) | leve fina (< 3 mm) y aislada · media 3–10 mm o ramificada · alta "piel de cocodrilo" o > 10 mm |
| 4 | `parche` | Reparación previa (asfalto de otro color o textura) | leve nivelado · media con desnivel o fisurado · alta hundido o suelto |
| 5 | `tapa` | Tapa de alcantarilla, cámara o rejilla | leve a nivel · media 1–3 cm de desnivel · alta hundida > 3 cm, rota o sin tapa |
| 6 | `obstaculo` | Escombro, piedra, cono, material de obra en la calzada | leve fácil de esquivar · media ocupa parte del carril · alta bloquea el carril |
| 7 | `linea_carril` | Línea de carril o de borde (blanca o amarilla) | — |
| 8 | `paso_peatonal` | Cebra | — |
| 9 | `via_buena` | Asfalto sin daño visible (también sirve concreto o adoquín en buen estado) | — |

Si en una foto hay dos cosas (un hueco sobre una línea), la clase es **la del daño** y en notas se escribe lo otro.

## 3. Configurar el celular (una sola vez)

| Qué | Android (Cámara) | iPhone |
|---|---|---|
| **Ubicación en las fotos** | Ajustes de la cámara → *Etiquetas de ubicación* / *Guardar ubicación*: **activado**; GPS del celular encendido | Ajustes → Privacidad → Localización → Cámara: *Mientras se usa* y **Ubicación exacta** |
| **Formato JPG** | Por defecto ya es JPG (no usar RAW) | Ajustes → Cámara → Formatos → **Más compatible** (JPG). HEIC también se acepta |
| Fecha y hora | Automáticas (de la red) | Automáticas |
| Sin zoom | Lente normal **1×** (no 0,5× ni 2×) | **1×** |
| Sin filtros ni modo retrato | Modo *Foto* normal; sin "belleza", sin filtros | Modo *Foto*; sin estilos |
| Orientación | **Horizontal** | **Horizontal** |

Antes de salir: tomar una foto de prueba y ver en la galería que tenga **ubicación** (en "Detalles"/"Información").

## 4. En cada punto: 4–5 fotos

Siempre en este orden, sin moverse del punto entre fotos (así se agrupan solas por GPS y hora):

| # | Ángulo (`angulo`) | Cómo |
|---|---|---|
| 1 | `contexto` | A 5–10 m, de pie, que se vea la calle, el daño y alrededores (sin placas ni caras) |
| 2 | `frente` | A 1,5–2 m, a la altura del pecho, mirando el daño en el sentido en que lo ve un conductor |
| 3 | `lado` | A 1,5–2 m, girando 90° alrededor del daño |
| 4 | `cenital` **con tarjeta** | Celular **paralelo al piso**, encima del daño, a 1–1,5 m. La **tarjeta ArUco** en el piso **junto** al daño (no encima), plana, completa en la foto; el daño también completo |
| 5 | termohigrómetro (si hay) | Foto de la pantalla del termohigrómetro dejado 1 min en el sitio, a la sombra |

- La tarjeta (`docs/tarjeta_aruco.pdf`) se imprime al **100 %** y se verifica con la regla impresa (debe dar 20 cm).
  Recortar, pegar en cartón y no doblar. Lado negro del marcador = **80 mm**.
- **Opcional (para validar la escala):** medir con una regla o metro el **largo** y el **ancho** del daño (cm) y
  anotarlos; se pasan al etiquetador (*Largo con regla*, *Ancho con regla*).
- La foto del termohigrómetro se marca **Excluir** en el etiquetador, y su lectura se escribe en la foto cenital del
  mismo punto (campos *Termohigrómetro*); la ingesta la copia a las demás fotos del sitio.

## 5. Variedad que buscamos

| Qué | Valores | Meta aproximada |
|---|---|---|
| Momento del día (sale solo de la hora) | madrugada (< 6 h), mañana (6–11), mediodía (11–14), tarde (14–18), noche (≥ 18) | Las 3 de día bien cubiertas; noche ≥ 10 % |
| Luz (`luz`) | sol, sombra, nublado, noche | Las 4 presentes en cada clase si se puede |
| Clima / piso | seco y **mojado** (`superficie_mojada`) | ≥ 15 % mojado (después de llover; no bajo aguacero) |
| Tipo de vía (`tipo_via`) | arterial (avenidas), colectora, local (barrio), destapada | Las 4; no solo el centro |
| Ángulo | contexto, frente, lado, cenital | ~ igual por clase (lo da el protocolo) |

## 6. Privacidad

- **No fotografiar personas** (esperar a que pasen) ni **placas legibles** (encuadrar al piso). Ni fachadas con gente,
  ni interiores, ni niños.
- La ingesta difumina caras y placas **automáticamente**, pero el detector puede fallar: en el etiquetador, si se ve una
  persona o una placa, oprimir **Excluir**.
- Las fotos **no se publican** ni se suben a redes. Viven en Drive (equipo) y en `data/` (ignorada por Git).
  Solo se publican, si acaso, muestras revisadas a mano.

## 7. Seguridad

- **Nunca** pararse en la calzada con tráfico. Fotos desde el andén o el borde; para las de cerca, en grupo de 2:
  uno toma la foto y el otro **vigila el tráfico** con chaleco reflectivo.
- El conductor **nunca** toma fotos. No fotografiar desde un carro en movimiento.
- De noche: solo en grupo, calles iluminadas, chaleco y linterna; si el sitio no es seguro, no se toma.
- Respetar propiedad privada y obras (no entrar a zonas cerradas).

## 8. Subir las fotos (sin WhatsApp)

**WhatsApp borra la ubicación y la fecha (EXIF) y comprime la foto: NO usarlo.** Tampoco "compartir enlace" de Google
Fotos (puede quitar la ubicación).

1. En la carpeta compartida de Drive del proyecto (`VIA_VIVA_fotos`), crear una subcarpeta por persona y día:
   **`AAAA-MM-DD_nombre`**, p. ej. `2026-11-05_pipe`, `2026-11-05_anzola`.
2. Subir las fotos **originales** con la app de Google Drive (botón *+* → *Subir*) o por cable USB al PC.
3. Andrés descarga las carpetas a `data/raw/fotos/` y corre la ingesta (`dataset/README.md`).

## 9. Lista para cada salida

- [ ] Celular con batería, ubicación activada, foto de prueba con ubicación.
- [ ] Tarjeta ArUco (verificada), regla o metro, termohigrómetro (si hay), chaleco.
- [ ] 4–5 fotos por punto en el orden de la sección 4.
- [ ] Al volver: subir a `AAAA-MM-DD_nombre` en Drive el mismo día.
