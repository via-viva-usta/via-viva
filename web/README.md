# web/ — interfaz web (dueño: Dany)

| Carpeta | Qué es |
|---|---|
| `en_linea/` | Sitio público: portada (`index.html`) y tablero (`tablero.html`) que leen de Supabase. Se publica con Netlify (`netlify.toml` en la raíz). Pruebas: `node --test tests/web/*.test.mjs` |
| `clasificador/` | CNN de fotos en el navegador del celular (`preparar.py --servir`). Queda aquí hasta que Dany decida si sigue en el prototipo |

`en_linea/marca.css` es el único sistema de estilos: lo usan este sitio y la app local (`viaviva/web/`).
`en_linea/config.js` (URL y clave **pública** de Supabase) no va en Git: lo arma Netlify al publicar o
`viaviva nube preparar` en el PC. El mapa estático viejo (`index.html` + `exportar.py`) salió del repo el 13-nov.
