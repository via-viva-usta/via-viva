# Contribuir a VÍA VIVA

`main` es la versión compartida y estable. Todo cambio entra por un Pull Request (PR) pequeño, con CI verde; nadie trabaja de forma permanente sobre `main`.

## Responsables

- **Dany:** interfaz, contenido e identidad de `web/`. `web/en_linea/marca.css` es la fuente única de tokens y estilos de marca compartidos. La app local puede tener CSS de composición propio en `viaviva/web/estilo.css`, enlazado a esos tokens.
- **AC:** motor y aplicación local de `viaviva/`, integraciones y coordinación del firmware. Los cambios de Raspberry Pi, sensores, captura o firmware se hacen en tareas separadas y no se mezclan con PR visuales.
- `CODEOWNERS` propone a Dany para cambios en `web/` y a AC para `viaviva/`. La protección de `main` debe exigir CI y revisión; CODEOWNERS solo se vuelve requisito cuando esa opción está activada en GitHub.

## Una vez por equipo

Instalar Git y clonar el repositorio. El clon debe iniciar en `main`:

```powershell
git clone https://github.com/via-viva-usta/via-viva.git
Set-Location via-viva
git switch main
git pull --ff-only origin main
```

En la app de Windows y macOS, instalar las dependencias una vez con `viaviva/instalar_pc.ps1` o `viaviva/instalar_mac.sh`. No incluir `.env`, tokens, claves, certificados ni datos de campo en Git.

## Flujo de Dany: interfaz web

```powershell
git switch main
git pull --ff-only origin main
git switch -c dani/descripcion-corta
# editar web/; mantener marca.css como única fuente de marca
node --test tests/web/*.test.mjs
git add web/ tests/web/
git commit -m "fix(web): descripción breve"
git push -u origin dani/descripcion-corta
gh pr create --base main --fill
```

El PR debe describir qué cambió y cómo se revisa. Dany no necesita copiar manualmente sus cambios a la app local: se integra la interfaz a `main`; la app comparte `marca.css` y recibe el código al usar **Actualizar VÍA VIVA** cuando no hay una sesión o video en curso. Los Deploy Previews ayudan a revisar; la publicación de producción debe usar `main` en Netlify (se confirma en la configuración del sitio).

## Flujo de AC: app local y motor

Crear una rama temporal `ac/<tarea>` desde `main`. Mantener separados los cambios de interfaz, motor, dependencias y firmware; para estos últimos, seguir las instrucciones de su módulo y especificar si se probaron en hardware real. Antes del PR, correr las pruebas y `ruff check` que correspondan. Claude Code puede trabajar en `viaviva/` cuando AC le delegue una tarea; debe respetar el flujo de ramas y no cambiar hardware/sensores dentro de un PR de interfaz.

## Ramas, PR y sincronización

- Una rama breve por tarea: `dani/<tarea>`, `ac/<tarea>` o el prefijo del área. No mantener ramas personales permanentes como `ac/software` o `dani/ui`; se vuelven largas y acumulan conflictos.
- PR pequeños hacia `main`; esperar todos los checks requeridos en verde y la revisión correspondiente. No empujar directamente a `main`.
- Al fusionar, borrar la rama de trabajo. Se conservan ramas con cambios aún no integrados; no reescribir historial ni usar `push --force`.
- En GitHub, proteger `main`, requerir los checks Python, Web y Firmware en cada PR, pedir una aprobación, bloquear force-push y permitir borrado automático de ramas fusionadas. Los tres workflows corren en PR aunque el cambio afecte otra carpeta, para que los checks requeridos no queden pendientes por filtros. La configuración efectiva se administra en GitHub, no en estos archivos.
- Los cambios visuales publicados en `main` se despliegan en Netlify si la rama de producción está configurada como `main`. Esa rama se confirma en Netlify; `netlify.toml` fija la carpeta publicada, no demuestra qué rama está activa.

## Actualizar la app instalada

- En Windows/macOS, abre VÍA VIVA con el icono o `viaviva app`. La app consulta el remoto oficial por Git y solo ofrece avanzar con `origin/main` en un clon limpio de la rama `main`.
- **Actualizar VÍA VIVA** no inicia si hay una sesión o un video activo. Si cambió `viaviva/requirements-pc.txt`, reinstala esas dependencias con el Python del entorno de VÍA VIVA y reinicia la app. Hay una reversa local a la versión anterior mientras el clon siga limpio.
- Sin internet, se conserva y se puede seguir usando la versión instalada. La caché local del mapa mantiene las calles de Tunja; los mapas de fondo, actualizaciones y la web pública necesitan red.
- La actualización automática está deshabilitada en la Pi y en los modos de servicio/terminal. La instalación de Pi y los sensores siguen un procedimiento técnico separado; no ejecutar `git pull` mientras el servicio o una captura estén activos.

## Datos y resultados

Nunca subir `.env`, tokens, claves (`include/secretos.h`), archivos de `06_CAMPO`, `data/raw/`, datos de la Alcaldía, fotos o videos. No inventar resultados: toda cifra del informe debe salir de código o mediciones; identificar las pruebas no hechas en hardware.
