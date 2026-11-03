# web/ — Mapa público (estático, sin backend)

`index.html` muestra, sobre OpenStreetMap (Leaflet 1.9.4):

- **tramos coloreados por riesgo** (quintiles, amarillo → rojo oscuro, con grosor creciente para leerse con daltonismo);
- **reportes ciudadanos** (rombos, color por estado: nuevo, confirmado, en reparación, reparado);
- **eventos detectados** (círculos: nodo y recorridos etiquetados);
- leyenda, control de capas, "© OpenStreetMap contributors" y un **aviso rojo DEMO** si la corrida del modelo es de prueba.

No hay servidor: los datos van en `datos.js`, que genera `exportar.py` desde SQLite.

```powershell
etl\.venv\Scripts\python web\exportar.py          # regenera web\datos.js
start web\index.html                              # abrir con doble clic también sirve
```

## Qué se publica y qué no

| Sale en el mapa | NO sale |
|---|---|
| Geometría de tramos (OSM, ODbL) y su riesgo | Datos de la Alcaldía (no se leen) |
| Reportes: tipo, estado, fecha, ubicación | Fotos, descripción y hash del usuario |
| Eventos: clase, origen, fecha, ubicación | Hash del vehículo, trayectorias, eventos simulados |

Coordenadas redondeadas a 5 decimales (~1 m). `datos.js` está en `.gitignore`: se regenera antes de publicar.

## Publicar en Netlify (NO publicar todavía)

Cuando el equipo lo decida (y el riesgo NO sea DEMO):

1. `etl\.venv\Scripts\python web\exportar.py`
2. Entrar a https://app.netlify.com/drop (cuenta gratuita) y **arrastrar la carpeta `web/`** completa.
   Netlify da una dirección `https://<nombre>.netlify.app`; se puede cambiar el nombre en *Site settings*.
3. Para actualizar: volver a exportar y arrastrar de nuevo la carpeta en *Deploys*.
   (Alternativa por consola: `npm install -g netlify-cli`, `netlify deploy --dir web` y luego `--prod`).

Las teselas vienen de `tile.openstreetmap.org`: su política permite uso liviano con atribución; si el mapa tiene mucho
tráfico, cambiar a otro proveedor de teselas.

## Estado (2-nov-2026)

Probado en el navegador con un servidor local (`python -m http.server`) y una **base de prueba** (corrida DEMO,
3 reportes de prueba y 40 eventos de recorridos sintéticos): cargan Leaflet (con verificación SRI), los tramos, los
reportes, los eventos, la leyenda, las capas y el aviso DEMO. Con la base real de hoy el mapa muestra los 5 775 tramos
en gris ("sin calcular"): aún no hay modelo entrenado, ni reportes, ni eventos. **No se ha publicado.**
