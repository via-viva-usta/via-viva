# Modelos 3D del menú

Modelos *low-poly* de **Kenney** (https://kenney.nl), licencia **CC0 1.0** (dominio público: se pueden usar, modificar y
publicar sin pedir permiso; el crédito no es obligatorio, pero se da). Se cargan con `<model-viewer>` (Google,
Apache-2.0) **solo cuando alguien abre el menú**, para que la portada siga siendo liviana. Total ≈ 268 KB.

| Opción del menú | Archivo | Origen (repositorio oficial, commit fijo) |
|---|---|---|
| Huecos para atender | `carreras/track-bump.glb` | `KenneyNL/Starter-Kit-Racing@2f2e5f2646dd`, `models/` |
| Riesgo por tramo | `ciudad/road-corner.glb` | `KenneyNL/Starter-Kit-City-Builder@4535092b740b`, `models/` |
| Tendencia | `carreras/vehicle-truck-yellow.glb` | `KenneyNL/Starter-Kit-Racing@2f2e5f2646dd` |
| Cómo funciona | `carreras/vehicle-truck-red.glb` | `KenneyNL/Starter-Kit-Racing@2f2e5f2646dd` |
| Cómo leer el mapa | `ciudad/road-intersection.glb` | `KenneyNL/Starter-Kit-City-Builder@4535092b740b` |
| Estado del prototipo | `ciudad/building-garage.glb` | `KenneyNL/Starter-Kit-City-Builder@4535092b740b` |

Cada GLB pide su paleta en `Textures/colormap.png` (relativa al archivo): por eso cada kit va en su carpeta con su propia
`Textures/colormap.png`. Los README de los dos repositorios dicen: «3D Models (CC0 licensed)»; el código de esos
repositorios es MIT y no se usa aquí. Se bajaron de GitHub porque kenney.nl y opengameart.org envían un certificado SSL
incompleto (no se desactivó la verificación).
