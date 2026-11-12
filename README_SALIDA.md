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
     dirección que respondió en `.env`. Solo si el iPhone tiene otra IP: `.\viaviva.cmd doctor --url http://<ip>`
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
3. La sesión queda en `02_VIA_VIVA\06_CAMPO\sesiones\sesion_AAAA-MM-DD_hhmm\` (en un PC sin esa carpeta:
   `via-viva\data\raw\sesiones\`; la consola dice cuál). **Nunca** al repositorio. Sin caras ni placas.
4. En phyphox: ⋮ → exportar CSV, como respaldo.

**Pasar la sesión al PC de AC (3 pasos):** (1) en el PC de la captura, clic derecho en la carpeta
`sesion_AAAA-MM-DD_hhmm` → *Comprimir* (zip); (2) pasar el zip por USB o el Drive restringido del equipo, con el
video de Pipe aparte; (3) en el PC de AC, descomprimir en `06_CAMPO\sesiones\`: aparece en `/sesiones` (ahí se importa
el video y se revisa). Para verla «en vivo»: `.\viaviva.cmd capture --replay <carpeta de la sesión>`.

## Practicar sin carro (cualquier PC)

```
.\viaviva.cmd capture --replay ejemplo --por-http --abrir
```
`ejemplo` es un recorrido **SINTÉTICO** de 3 min que se crea solo (no hacen falta datos de campo); también sirve un
export real de phyphox (.zip o carpeta). Con `--velocidad 5` va 5 veces más rápido; los eventos quedan **simulados**.

## PC de otra persona (Lenovo de Anzola; Mac de Dani)

- **Windows (camino principal):** instalar Git y Python 3.11 (`winget install Git.Git Python.Python.3.11`; ffmpeg
  opcional: `winget install Gyan.FFmpeg`). `git clone` del repo, rama `ac/cierre-software`, y en la carpeta `via-viva`:
  `powershell -ExecutionPolicy Bypass -File viaviva\instalar_pc.ps1`. No hace falta ningún `.env` ni clave: el instalador
  crea uno vacío; el PIN de `/marcar` sale en la consola (o fijo con `VIAVIVA_PIN` en `.env`).
- **Mac (sin probar en Mac):** `bash viaviva/instalar_mac.sh` (Homebrew: Python 3.11 y ffmpeg) y luego `./viaviva.sh doctor`
  y `./viaviva.sh capture --abrir`. macOS pregunta si Python acepta conexiones entrantes: **Permitir**. Se marca en
  `/captura` o en el celular (las teclas de la consola son solo de Windows).
- **Docker (plan B, sin probar):** (1) instalar Docker Desktop; (2) `docker compose build`; (3) conectarse al WiFi del
  iPhone; (4) `docker compose run --rm viaviva doctor`; (5) `docker compose up` y abrir `http://localhost:8000/captura`.
  Sesiones en `data\sesiones_docker\`; el celular usa la IP del PC (`ipconfig`), no la que diga la consola.
- **Todo bien:** el doctor dice **LISTO**; la consola muestra «Grabando: sesion_…», la dirección y el PIN; `/captura`
  muestra la señal moviéndose y el GPS.
- **Errores típicos:** «Falta Python» → instalarlo y abrir otra consola · «no se reconoce viaviva.cmd» en PowerShell →
  escribir `.\viaviva.cmd` · «Alcance a phyphox» → WiFi del iPhone, acceso remoto activado y ▶ en phyphox · el celular
  no abre `/marcar` → Firewall de Windows: permitir Python en **red privada** y marcar el WiFi del iPhone como red privada · «Puerto
  8000 ocupado» → ya hay una captura abierta: cerrarla con Q.
- **iPhone que filma (Pipe):** Ajustes → Cámara → Formatos → **Más compatible** (H.264): así el video no necesita
  conversión.
