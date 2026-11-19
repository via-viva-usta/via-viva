# Paquete para Windows: estado actual y evaluación (19-nov-2026)

## Lo que existe hoy (no es un `.exe` independiente)

`viaviva/instalar_pc.ps1`:
- **Exige Python 3.11–3.13 instalado.** Si falta, pide `winget install Python.Python.3.11`.
- Crea el entorno `viaviva\.venv`, que mide **439 MB** en el PC de AC. Lo más pesado: scipy 119 MB, OpenCV 111 MB,
  scikit-learn 47 MB y numpy 37 MB.
- Pone un icono en el Escritorio y en el menú Inicio. La app se abre como ventana propia de Edge o Chrome sobre el
  servidor local.
- ffmpeg es opcional: solo hace falta para convertir los videos HEVC del iPhone.

Probado: instalación limpia en el PC de AC desde un clon nuevo (#38).
**Sin probar:** un Windows recién instalado, sin Python ni Git.

## Opciones

| Opción | Qué entrega | Tamaño estimado | A favor | En contra |
|---|---|---|---|---|
| **A. Actual** (script + entorno de Python + navegador) | Icono que abre la app | ~0,5 GB tras instalar | Ya funciona y se actualiza con **Actualizar** (git) | Requiere Python, Git e internet para instalar; no es un solo archivo |
| **B. Python embebido portable** (zip de python.org + paquetes ya instalados + `VIA VIVA.cmd`) | Carpeta que se descomprime y abre | ~0,5 GB descomprimido, ~200 MB en zip (estimado) | Sin compilar; nada escondido; funciona sin internet; no toca el sistema | **Actualizar** deja de usar git: hay que bajar otro zip |
| **C. Instalador Inno Setup sobre B** | `VIA_VIVA_instalador.exe` con icono y desinstalador | Como B | La experiencia habitual de Windows | Sin firma de código, SmartScreen avisa «editor desconocido» |
| **D. PyInstaller `--onedir`** | `viaviva.exe` y su carpeta | ~0,4–0,6 GB (estimado) | Un ejecutable real | Antivirus con falsos positivos frecuentes; archivos web, certificados y ffmpeg hay que declararlos a mano; depuración difícil |

**Recomendación:** B, y después C cuando B pase la prueba en limpio. D no compensa para un prototipo.

Para reducir el tamaño, se podría quitar scipy del paquete de campo si nada del flujo de la app lo importa. Hay que
medirlo antes de quitarlo.

## Prueba obligatoria antes de llamarlo «listo para distribuir»

Hace falta un **Windows limpio**, sin Python, Git, ffmpeg ni sesión de GitHub:
- **Windows Sandbox.** Se activa en «Características de Windows»; requiere Windows Pro y lo activa AC.
- O una máquina virtual.

Pasos:
1. Copiar el zip o el instalador. Comprobar que abre sin internet y que el icono arranca la app.
2. Grabar 1 minuto con el **ejemplo** y abrir Sesiones, Revisión y Tablero. Cerrar y comprobar que la sesión quedó
   guardada.
3. Conectar phyphox (iPhone A) por el hotspot. Comprobar que el celular abre `/marcar` y `/camara` por HTTPS con el
   certificado propio.
4. Desinstalar o borrar la carpeta y comprobar que no quedan servicios ni tareas programadas.

Hasta pasar esa prueba, la entrega oficial sigue siendo la opción A.
