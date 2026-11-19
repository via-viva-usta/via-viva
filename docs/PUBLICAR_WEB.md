# Publicar el sitio en línea con Netlify (pasos de AC)

El sitio es `web/en_linea/` (portada + tablero de Dany), estático y sin compilación. Netlify lo publica **desde GitHub**:
cada PR recibe una vista previa con su propia dirección y lo que entra a `main` queda publicado. Claude no crea la
cuenta ni inicia sesión: estos pasos los hace AC una vez.

## Qué hace Netlify en cada publicación (ya está en el repo)

- `netlify.toml` → publica `web/en_linea` y antes corre `node herramientas/config_web.mjs`.
- `config_web.mjs` escribe `web/en_linea/config.js` con `SUPABASE_URL` y `SUPABASE_CLAVE_PUBLICA`, tomadas de las
  variables del sitio. **Nunca** usa la clave secreta (`service_role`): si alguien la pone por error en
  `SUPABASE_CLAVE_PUBLICA` y también en `SUPABASE_CLAVE`, la publicación falla a propósito.
- **Sin variables** (o en una vista previa sin ellas), `config.js` queda vacío y el tablero abre en **modo de prueba**:
  datos de demostración en el navegador, con la franja de aviso. Sirve para revisar el diseño sin Supabase.
- `web/en_linea/datos/tramos.geojson` (calles de OSM, ODbL, ~1,3 MB) va en el repo: no hay que subirlo aparte.

## Pasos (una vez)

1. **Cuenta:** entrar en https://app.netlify.com con *Sign up with GitHub* usando la cuenta `andresscardens`.
2. **Importar el repo:** *Add new project → Import an existing project → GitHub* → autorizar solo la organización
   `via-viva-usta` (botón *Configure the Netlify app on GitHub* → *Only select repositories* → `via-viva`).
3. **Ajustes de publicación** (Netlify los lee de `netlify.toml`; verificar que queden así):
   | Campo | Valor |
   |---|---|
   | Branch to deploy | `main` |
   | Base directory | *(vacío)* |
   | Build command | `node herramientas/config_web.mjs` |
   | Publish directory | `web/en_linea` |
4. **Variables** (*Project configuration → Environment variables → Add a variable*), después de crear Supabase
   (`docs/NUBE.md`, pasos 1–5):
   | Clave | Valor | Contextos |
   |---|---|---|
   | `SUPABASE_URL` | `https://<id>.supabase.co` | *Production* y *Deploy previews* |
   | `SUPABASE_CLAVE_PUBLICA` | la clave **anon / publishable** | *Production* y *Deploy previews* |
   Nunca agregar `SUPABASE_CLAVE` (la secreta) en Netlify. Si se quiere que las vistas previas de Dany usen solo datos
   de prueba, dejar esas dos variables **solo** en *Production*.
5. **Vistas previas por PR:** *Project configuration → Build & deploy → Branches and deploy contexts* →
   *Deploy previews: Any pull request against your production branch*. Netlify comenta en cada PR el enlace de la vista
   previa (Dany revisa ahí antes de aprobar).
6. **Publicar:** *Deploys → Trigger deploy → Deploy project*. En el registro debe aparecer
   `config.js listo para https://<id>.supabase.co` (o `modo demostración` si aún no hay variables).
7. **Nombre:** *Project configuration → Change project name* → p. ej. `via-viva-tunja` → `https://via-viva-tunja.netlify.app`.

## Comprobar

- `https://<sitio>/` abre la portada y `https://<sitio>/tablero.html` el tablero (sin sesión: datos de prueba).
- `https://<sitio>/tablero.html?entrar` pide correo: con una cuenta invitada en Supabase y su perfil, muestra los datos
  reales (RLS: sin sesión no se lee nada; ver `docs/SEGURIDAD.md`).
- `https://<sitio>/config.js` muestra la URL y la clave **pública**; nunca la secreta.

## Probar en local sin Netlify

```
node herramientas/config_web.mjs          # sin variables: config.js en modo demostración
python -m http.server 8000 -d web/en_linea
```
Abrir http://localhost:8000/tablero.html. Pruebas: `node --test tests/web/*.test.mjs`.

La alternativa manual anterior (`npx netlify deploy --prod --dir web/en_linea` con `viaviva nube preparar`) sigue
funcionando, pero no da vistas previas por PR.
