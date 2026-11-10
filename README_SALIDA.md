# Salida de campo con phyphox — 1 página

**Quién hace qué:** iPhone 1 fijo en el carro (phyphox + punto de acceso) · PC de AC con la captura · Anzola marca
(teclado del PC o su celular) · Pipe filma con el iPhone 2 (solo video, sin software). Máx. **30 km/h**;
**1 minuto quieto** al inicio y al final.

## 1. Antes de arrancar (en el parqueadero)

1. **iPhone 1:** phyphox → experimento **«VÍA VIVA 2.0»** → menú ⋮ → **Permitir acceso remoto** (en el iPhone muestra
   `http://172.20.10.1`, puerto 80; no hace falta anotarla: el doctor la encuentra sola) → ▶ para empezar a medir. Activa el **Punto de acceso personal**.
2. **PC:** conéctate al WiFi del iPhone 1. Doble clic en **`SALIDA_DE_CAMPO.cmd`** (carpeta `via-viva`).
   Primero corre el **doctor**: debe decir **LISTO**. Si dice FALTA, haz lo que indica y vuelve a abrirlo.
   - El doctor prueba solo los puertos **80 y 8080**, lee de phyphox los nombres reales de los buffers y deja la
     dirección que respondió en `.env`. Solo si el iPhone tiene otra IP: `viaviva.cmd doctor --url http://<ip>`
     (queda guardada para la captura).
   - La primera vez Windows pregunta por el **Firewall**: permitir en **redes privadas** (si no, el celular de Anzola
     no podrá abrir `/marcar`).
3. Con LISTO, la captura **empieza a grabar sola** y abre el navegador en `http://localhost:8000/captura`. La consola
   muestra la **dirección y el PIN** para el celular de Anzola.
4. **Celular de Anzola** (mismo WiFi): abrir `http://<ip-del-PC>:8000/marcar` y escribir el PIN.
5. **Sincronía con el video:** en el PC o en el celular, abrir `/sync` → Pipe filma la pantalla → **DESTELLO**.
   Repetirlo **al inicio y al final** de cada toma.
6. **1 minuto quieto** con el motor encendido. Luego, a rodar.

## 2. Durante el recorrido: marcar

| Tecla (PC) o botón (celular) | 1 | 2 | 3 | 4 | 5 | 6 | 7 | U |
|---|---|---|---|---|---|---|---|---|
| Clase | hueco | resalto | grieta | parche | tapa | obstáculo | vía buena | **deshacer la última** |

- Se marca **cuando la llanta pasa**. El programa corre la marca **1 s hacia atrás** (tiempo de reacción).
- En la consola del PC: **S** = marca de sincronía, **Q** = terminar.
- Si se cae el WiFi del iPhone, la captura **avisa y reconecta sola**. Lo del corte no se pierde mientras phyphox siga
  midiendo (▶). **No** detengas phyphox hasta terminar.

## 3. Al terminar

1. **1 minuto quieto**, destello en `/sync` y **Q** en la consola del PC (o Ctrl+C).
2. La consola muestra el **RESUMEN**: duración, pérdidas, marcas por clase, km, velocidad máxima y **avisos** (si
   faltó el minuto quieto —se toleran hasta 5 km/h de ruido del GPS—, si se pasó de 30 km/h…).
3. La sesión queda en `02_VIA_VIVA\06_CAMPO\sesiones\sesion_AAAA-MM-DD_hhmm\`. Súbela al **Drive restringido** junto
   con el video de Pipe. **Nunca** al repositorio. Sin caras ni placas.
4. En phyphox: ⋮ → exportar CSV → Drive (`06_CAMPO/phyphox/AAAA-MM-DD/`), como respaldo.

## Practicar sin carro

```
viaviva.cmd capture --replay "..\..\06_CAMPO\phyphox\2026-11-07\VÍA VIVA 2.0 2026-11-07 09-42-16.zip" --por-http --abrir
```
Reproduce una salida real como si fuera en vivo (con `--velocidad 5` va 5 veces más rápido). Los eventos quedan
marcados como **simulados**.
