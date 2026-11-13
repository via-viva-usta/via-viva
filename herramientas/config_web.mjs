// Netlify: arma web/en_linea/config.js al publicar, con las variables del sitio (Site configuration → Environment
// variables). Así ninguna clave va en Git. Solo la clave PÚBLICA (anon) de Supabase: es pública por diseño y sin sesión
// no lee nada (RLS en viaviva/supabase_esquema.sql). Sin variables, el sitio queda en modo demostración.
//   node herramientas/config_web.mjs        (lo corre Netlify: `command` en netlify.toml)
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const url = (process.env.SUPABASE_URL || '').trim().replace(/\/+$/, '');
const publica = (process.env.SUPABASE_CLAVE_PUBLICA || '').trim();
if (publica && publica === (process.env.SUPABASE_CLAVE || '').trim()) {
  console.error('SUPABASE_CLAVE_PUBLICA es igual a la clave de servicio: NO se publica. Use la clave anon.');
  process.exit(1);
}
if (url && !/^https:\/\/[a-z0-9-]+\.supabase\.co$/.test(url)) {
  console.error('SUPABASE_URL no parece la URL de un proyecto de Supabase (https://<id>.supabase.co).');
  process.exit(1);
}
const destino = fileURLToPath(new URL('../web/en_linea/config.js', import.meta.url));
writeFileSync(destino,
  '// Generado al publicar (herramientas/config_web.mjs). No se sube a Git.\n' +
  `window.VIAVIVA = ${JSON.stringify({ supabaseUrl: url, supabaseClave: publica })};\n`);
console.log(url && publica ? `config.js listo para ${url}` : 'config.js sin Supabase: el sitio queda en modo demostración.');
