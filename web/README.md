# web/ — interfaz web (dueño: Dany)

Sitio público de VÍA VIVA: portada y tablero de huecos y riesgo de Tunja. Estático (HTML + CSS + JS sin compilar),
publicado con Netlify desde `main`. Pruebas: `node --test tests/web/*.test.mjs` (también en el check `node-test`).

## Qué hay en cada archivo (`web/en_linea/`)

| Archivo | Qué es |
|---|---|
| `index.html` · `inicio.css` · `inicio.js` | Portada: hora de Tunja, secciones que aparecen por partes, cifras animadas |
| `tablero.html` | Tablero: mapa, cifras, filtros, «Para atender», riesgo por tramo y tendencia |
| `app.js` | Lógica del tablero: sesión con Supabase, filtros, paneles, descargas; sin sesión, datos de **prueba** marcados |
| `carga.js` | Trae los datos (Supabase con sesión o datos de prueba en el navegador) y los prepara para la interfaz |
| `mapa.js` | Mapa MapLibre + OpenFreeMap en dos modos («huecos» y «riesgo por tramo») para que los colores no se mezclen |
| `reglas.js` | Nombres, niveles, prioridad, fechas y CSV en un solo lugar (sin dependencias: lo prueba Node). Las fórmulas son las del tablero local: si cambian aquí, cambiar `viaviva/web/tablero.html` y `viaviva/almacen.py` |
| `menu.js` + `modelos/` | Menú con modelos 3D (Kenney, CC0); `<model-viewer>` se baja solo al abrir el menú |
| `vigia.js` | Si el tablero no arranca en 12 s, avisa y ofrece reintentar |
| `tema.js` | Oscuro por defecto y claro con ◐ (llave `vv_tema`); va aparte porque la CSP no permite scripts en línea |
| `marca.css` | **Única fuente de estilos de marca**: la usan este sitio y la app local (`viaviva/web/estilo.css`) |
| `estilo.css` | Composición del tablero sobre Pico.css y colores con significado (estado del hueco, riesgo) |
| `fuentes/` · `img/` | Archivo Black e Inter (OFL, locales: la CSP no permite Google Fonts) · imágenes de la portada |
| `datos/tramos.geojson` | 5 775 calles de Tunja (OpenStreetMap, ODbL, 1,3 MB), en el repo |
| `config.js` | **No va en Git.** URL y clave **pública** de Supabase; lo arma Netlify al publicar (`herramientas/config_web.mjs`) |

Librerías externas (jsDelivr, versión fija): Pico.css 2.1.1, MapLibre GL 6.17.0 y model-viewer 4.4.0. Las cabeceras de
seguridad (CSP y otras) están en `netlify.toml`, en la raíz: si se agrega otra librería o dominio, hay que permitirlo ahí.

`web/clasificador/` (CNN de fotos en el navegador del celular, `preparar.py --servir`) queda aquí hasta que Dany decida
si sigue en el prototipo.

## Verlo en local (sin Netlify)

Desde la carpeta `via-viva`:

```
node herramientas/config_web.mjs              # config.js en modo de prueba (sin Supabase)
python -m http.server 8080 -d web/en_linea    # o cualquier servidor estático
```

Abrir http://localhost:8080/ (portada) y http://localhost:8080/tablero.html (tablero con datos de prueba y la franja
de aviso). Para revisar en el celular: misma red WiFi y `http://<IP del PC>:8080/`. Antes del PR:
`node --test tests/web/*.test.mjs`.

## Cómo se publica

Netlify toma `main` y publica `web/en_linea` (`netlify.toml`). Antes corre `node herramientas/config_web.mjs`, que arma
`config.js` con las variables del sitio `SUPABASE_URL` y `SUPABASE_CLAVE_PUBLICA`. Sin variables, el sitio queda en modo
de prueba. Cada PR recibe una **vista previa** con su propio enlace, que Netlify comenta en el PR; ahí se revisa antes de
aprobar. Los pasos para crear el sitio (los hace AC) están en `docs/PUBLICAR_WEB.md`.
