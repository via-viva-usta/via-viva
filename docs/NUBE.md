# Tablero en línea y sincronización (Supabase + Netlify)

**Fuente de verdad:** la base SQLite de la Pi (o del PC). La nube es una **copia** para consultar desde cualquier lugar.
Diseño y licencias: `docs/DISENO.md`. Seguridad: `docs/SEGURIDAD.md`.

```
Pi / PC (SQLite) ──cola con reintentos──► Supabase: eventos_publicos · huecos_publicos · riesgo_publico
       ▲                                         │ RLS: solo usuarios con perfil leen
       └──── cambios_remotos (estado pedido) ◄────┘ editores piden cambios en el tablero en línea
Netlify: web/en_linea (estático) ──supabase-js (clave pública + sesión)──► Supabase
```

## Lo que hace AC (inicios de sesión y claves; Claude no los hace)

1. **Supabase:** entrar en https://supabase.com con `andresscardens@gmail.com` → *New project* (región `us-east-1` o
   la más cercana; contraseña de la base generada por Supabase y guardada solo en tu gestor de contraseñas).
2. *SQL Editor* → pegar **todo** `viaviva/supabase_esquema.sql` → *Run*.
3. *Authentication → Users → Invite*: los 4 del equipo, la Alcaldía y los docentes. *Authentication → Sign In / Up*:
   **desactivar** "Allow new users to sign up" (no hay registro abierto).
4. Rol de cada uno (SQL Editor; cambiar correos):
   ```sql
   insert into perfiles (usuario_id, nombre, rol)
   select id, 'Andrés Cárdenas', 'editor' from auth.users where email = 'correo-de-andres@…';
   -- repetir: editor ×4 (equipo), 'alcaldia' y 'docente' para los de solo lectura
   ```
5. *Project Settings → API*: copiar la **URL**, la clave **anon/publishable** y la **service_role/secret** al `.env`
   (abrirlo con el editor; nunca por chat):
   ```
   SUPABASE_URL=https://xxxx.supabase.co
   SUPABASE_CLAVE_PUBLICA=<anon / publishable>     # va a la página (es pública por diseño)
   SUPABASE_CLAVE=<service_role / secret>          # SOLO en el .env de la Pi/PC que sincroniza
   ```
6. **Netlify:** en una consola, `npx netlify login` (se abre el navegador; inicia sesión AC) y luego, desde `via-viva`:
   ```
   viaviva.cmd nube preparar
   npx netlify deploy --prod --dir web/en_linea
   ```
   (o arrastrar la carpeta `web/en_linea` en https://app.netlify.com/drop). Dar la URL a la Alcaldía y a los docentes.

## Cómo queda funcionando

- La captura (Pi o PC) sincroniza cada 30 s si hay internet: **eventos** y **huecos** (eventos agrupados con su estado)
  y el **riesgo** de la última corrida. Lista blanca de columnas: sin velocidad, sin vehículo, sin fotos, sin nombres
  de quien maneja, sin notas, sin datos crudos de la Alcaldía. Lo simulado/DEMO nunca sube.
- Sin internet la cola espera (reintentos a 30 s, 1 min, 2 min… hasta 1 h) y no se duplica nada (`id_origen`).
- Un **editor** cambia el estado de un bache en línea → `cambios_remotos` → la Pi lo aplica en SQLite (con historial,
  usuario `nube:<correo>`) y lo vuelve a subir. Si el bache no existe, queda `rechazado`.
- `?kiosco=1` = pantalla fija para la Alcaldía (sin controles, se refresca cada minuto, pantalla siempre encendida).
- `?demo=1` = datos inventados en el navegador para mostrar el diseño sin cuenta (con aviso rojo).
- El plan gratuito de Supabase **pausa** el proyecto tras una semana sin actividad; la sincronización diaria suele
  evitarlo (sin garantía). Se restaura desde el panel.

Probar sin internet: `viaviva.cmd sync --una-vez` muestra lo que está en la cola.
