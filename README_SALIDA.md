# Salida de campo con phyphox — 1 página

| Rol | Quién | Qué hace |
|---|---|---|
| iPhone A (fijo en el carro) | Anzola | phyphox «VÍA VIVA 2.0» con acceso remoto y ▶ + **Punto de acceso personal** |
| PC de captura (Lenovo, Windows) | Anzola | Icono **VÍA VIVA** del escritorio (la app abre en su ventana); marca con el teclado: 1–7, U deshacer |
| iPhone B (video) | Pipe | **Solo video**; filma el destello de `/sync` al inicio y al final (opcional: cámara en vivo, abajo) |
| Celular extra (opcional) | un tercero, si va | `/marcar` con el PIN; no es el iPhone A ni el B |
| Conductor | — | Solo conduce. Máx. **30 km/h**; **1 minuto quieto** al inicio y al final |

## 0. Una vez: el experimento «VÍA VIVA 2.0» en el iPhone A

- **Opción 1 (recomendada, sin pasar archivos):** phyphox → **+** → **Experimento simple** → título `VÍA VIVA 2.0`;
  sensores **Acelerómetro** (el que incluye la gravedad, no «aceleración lineal»), **Giroscopio** y **Ubicación (GPS)**;
  frecuencia **0** (la máxima) o, si pide un número, **100 Hz** → crear. Queda en la lista de experimentos.
- **Opción 2 (el mismo archivo del 7-nov):** enviarse `config/phyphox/VIA_VIVA_2.0.phyphox` (está en el repo, sin datos)
  por correo o el Drive del equipo → en el iPhone, tocar el archivo (app Archivos) → abrir con **phyphox** → si lo
  ofrece, **Guardar experimento** para que quede en la lista.
- **Comprobar:** con el Lenovo en el WiFi del iPhone A, `.\viaviva.cmd doctor` debe decir OK en «Buffers» y
  «Flujo 100 Hz». Ninguna de las dos opciones se ha probado aún en el iPhone de Anzola.

## 1. Antes de arrancar (en el parqueadero)

1. **iPhone A (Anzola):** **Ajustes → Pantalla y brillo → Bloqueo automático → Nunca**; activa el **Punto de acceso
   personal** (si el Lenovo no ve la red: «Maximizar compatibilidad»). phyphox → **«VÍA VIVA 2.0»** → menú ⋮ →
   **Permitir acceso remoto** (muestra `http://172.20.10.1`; no hace falta anotarla) → **▶**. Fíjalo en el soporte.
2. **Lenovo (Anzola):** conéctalo al WiFi del iPhone A y doble clic en el icono **VÍA VIVA** del escritorio: la app
   abre en su propia ventana, en **Campo**. El panel **Conexión** dice en vivo qué falta:
   - **Red del PC:** la IP debe ser `172.20.10.x` (la red del iPhone). **phyphox · iPhone A:** «Conectado», puerto 80,
     latencia en ms y **~100 Hz reales**. Si dice «No detectado»: **Probar conexión** explica qué revisar y
     **Reintentar con el iPhone A** vuelve a buscarlo (puertos 80 y 8080).
   - La primera vez Windows pregunta por el **Firewall**: permitir en **redes privadas** (hace falta para el celular
     extra y para la cámara del iPhone B).
   - Alternativa sin icono: `SALIDA_DE_CAMPO.cmd` (doctor + captura en consola, como antes).
3. Con phyphox conectado, toca **Iniciar grabación**. El panel muestra el **PIN y un QR** por si va un celular extra
   (lo escanea y queda dentro de `/marcar` sin escribir nada).
4. **Sincronía con el video:** en el Lenovo, abre `http://localhost:8000/sync`; **Pipe** empieza a grabar con el
   iPhone B, apunta a la pantalla del Lenovo y Anzola pulsa **DESTELLO**. Repetirlo **al inicio y al final** de cada
   toma (si Pipe corta el video, destello otra vez al empezar el clip nuevo).
5. **1 minuto quieto** con el motor encendido. Luego, a rodar.

## 2. Durante el recorrido: marcar (Anzola, en el teclado del Lenovo)

| Tecla del Lenovo (o botón de `/marcar`) | 1 | 2 | 3 | 4 | 5 | 6 | 7 | U |
|---|---|---|---|---|---|---|---|---|
| Clase | hueco | resalto | grieta | parche | tapa | obstáculo | vía buena | **deshacer la última** |

- Se marca **cuando la llanta pasa**. El programa corre la marca **1 s hacia atrás** (tiempo de reacción).
- **1–7 y U** funcionan en la ventana de la app (y en la consola si se usó `SALIDA_DE_CAMPO.cmd`, donde además
  **S** = sincronía y **Q** = terminar).
- Si se cae el WiFi del iPhone A, la captura **avisa y reconecta sola**. Lo del corte no se pierde mientras phyphox
  siga midiendo (▶). **No** detengas phyphox hasta terminar.

## 3. Al terminar

1. **1 minuto quieto**, destello en `/sync` (Pipe lo filma) y **Detener y guardar** en la app (cerrar la ventana
   también guarda la grabación abierta).
2. En **Sesiones** queda la salida con su **RESUMEN**: duración, pérdidas, marcas por clase, km, velocidad máxima y **avisos** (si
   faltó el minuto quieto —se toleran hasta 5 km/h de ruido del GPS—, si se pasó de 30 km/h…).
3. La sesión queda en `02_VIA_VIVA\06_CAMPO\sesiones\sesion_AAAA-MM-DD_hhmm\` (en un PC sin esa carpeta:
   `via-viva\data\raw\sesiones\`; la consola dice cuál). **Nunca** al repositorio. Sin caras ni placas.
4. En el iPhone A: phyphox ⋮ → exportar CSV, como respaldo. Pipe pasa el video **original** del iPhone B (cable,
   AirDrop o Drive restringido; **nunca WhatsApp**: comprime y cambia la fecha).

**Pasar la sesión al PC de AC (3 pasos):** (1) en el Lenovo, clic derecho en la carpeta
`sesion_AAAA-MM-DD_hhmm` → *Comprimir* (zip); (2) pasar el zip por USB o el Drive restringido del equipo, con el
video de Pipe aparte; (3) en el PC de AC, descomprimir en `06_CAMPO\sesiones\`: aparece en `/sesiones` (ahí se importa
el video y se revisa). Para verla «en vivo»: `.\viaviva.cmd capture --replay <carpeta de la sesión>`.

## Practicar sin carro (cualquier PC)

En la app: panel **Conexión → Usar el ejemplo**. O en consola: `.\viaviva.cmd capture --replay ejemplo --por-http --abrir`.
`ejemplo` es un recorrido **SINTÉTICO** que se crea solo: 5,75 km por calles reales de Tunja desde la Plaza de Bolívar,
15–29 km/h, frenadas en las esquinas y 16 baches puestos a mano (huecos, resaltos y tapas) que el detector ve en el
mapa y en la señal; da vueltas sin parar. No son resultados. También sirve un export real de phyphox (.zip o carpeta).

## Cámara en vivo (opcional)

- **Webcam del PC** (funciona con la app en el Lenovo): tarjeta **Cámara en vivo** → **Encender** → con la grabación
  andando, **Grabar con la sesión**. El video queda dentro de la sesión, ya sincronizado por el reloj del PC (no hace
  falta destello) y se ve en **Revisión**. Probado con una cámara sintética en Edge; con la webcam real, pruébelo una vez.
- **iPhone B en vivo (SIN PROBAR en un iPhone real):** Safari solo da la cámara en HTTPS. La app abre además
  `https://<IP del Lenovo>:8443` con una autoridad local propia. Una vez por iPhone: (1) en Safari abrir
  `http://<IP del Lenovo>:8000/ca.crt` → «Permitir» (perfil descargado); (2) Ajustes → General → **VPN y gestión de
  dispositivos** → «VIA VIVA autoridad local» → Instalar; (3) Ajustes → General → Información → **Ajustes de confianza
  de certificados** → activarla. Luego abrir `https://<IP del Lenovo>:8443/camara`, escribir el PIN, **Encender cámara**
  y **Grabar con la sesión**: el Lenovo ve la imagen (unos 1–2 cuadros por segundo) y el video entra a la sesión.
  Si algo de esto falla, Pipe filma como siempre (normal, con destello) y el video se importa después en **Revisión**.

## Instalar en el Lenovo de Anzola (y opciones: Mac de Dani, Docker)

- **Windows (camino principal):** instalar Git y Python 3.11 (`winget install Git.Git Python.Python.3.11`; ffmpeg
  opcional: `winget install Gyan.FFmpeg`). `git clone` del repo, rama `ac/cierre-software`, y en la carpeta `via-viva`:
  `powershell -ExecutionPolicy Bypass -File viaviva\instalar_pc.ps1`. Deja el icono **VÍA VIVA** en el escritorio y en
  el menú Inicio (abre la app en su ventana de Edge, sin consola). No hace falta ningún `.env` ni clave: el instalador
  crea uno vacío; el PIN de `/marcar` sale en el panel de conexión (o fijo con `VIAVIVA_PIN` en `.env`).
- **Mac de Dani (opcional, sin probar en Mac):** `bash viaviva/instalar_mac.sh` (Homebrew: Python 3.11 y ffmpeg) deja
  «VIA VIVA.app» en ~/Applications; en consola: `./viaviva.sh app`, `./viaviva.sh doctor`, `./viaviva.sh capture --abrir`. macOS pregunta si Python acepta conexiones entrantes
  y si Terminal puede usar la red local: **Permitir**. Se marca con 1–7 y U en la página `/captura` (la consola no
  lee teclas fuera de Windows; se termina con Ctrl+C).
- **Docker (plan B, NO probado en Docker):** hay `Dockerfile` y `docker-compose.yml`, pero aquí no había Docker: solo se
  comprobó que la app corre (doctor y `--replay ejemplo --por-http`) con los mismos archivos que entran en la imagen.
  Pasos: `docker compose build` → `docker compose run --rm viaviva doctor` → `docker compose up` →
  `http://localhost:8000/captura`. En Docker se marca con 1–7 y U en la página `/captura`.
- **Todo bien:** el panel **Conexión** dice «Todo listo para grabar» (phyphox conectado, ~100 Hz); la señal se mueve,
  el mapa muestra el recorrido y la velocidad cambia. Sin internet el mapa muestra igual las calles de Tunja (aviso
  amarillo «Sin internet»).
- **Errores típicos:** «Falta Python» → instalarlo y abrir otra consola · «no se reconoce viaviva.cmd» en PowerShell →
  escribir `.\viaviva.cmd` · «Alcance a phyphox» → WiFi del iPhone, acceso remoto activado y ▶ en phyphox · el celular
  no abre `/marcar` → Firewall de Windows: permitir Python en **red privada** y marcar el WiFi del iPhone como red privada · «Puerto
  8000 ocupado» → ya hay una captura abierta: el icono abre otra ventana hacia ella; si es una consola, cerrarla con Q.
- **iPhone B (Pipe):** Ajustes → Cámara → Formatos → **Más compatible** (H.264) y Grabar video → 1080p a 30 cps: así
  el video no necesita conversión.
