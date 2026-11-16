// herramientas/config_web.mjs (lo corre Netlify al publicar): arma config.js con la clave PÚBLICA y nunca la de servicio.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync, unlinkSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const script = fileURLToPath(new URL('../../herramientas/config_web.mjs', import.meta.url));
const destino = fileURLToPath(new URL('../../web/en_linea/config.js', import.meta.url));
const correr = (env) => spawnSync(process.execPath, [script], {env: {PATH: process.env.PATH, ...env}, encoding: 'utf8'});
const respaldo = existsSync(destino) ? readFileSync(destino) : null;   // no pisar el config.js local del PC
const restaurar = () => { if (respaldo === null) { if (existsSync(destino)) unlinkSync(destino); } };

test('sin variables, config.js queda en modo demostración', () => {
  if (respaldo !== null) return;                                  // hay uno local: no se toca
  const r = correr({});
  assert.equal(r.status, 0);
  assert.match(readFileSync(destino, 'utf8'), /"supabaseUrl":"","supabaseClave":""/);
  restaurar();
});

test('con la URL y la clave pública, las escribe', () => {
  if (respaldo !== null) return;
  const r = correr({SUPABASE_URL: 'https://abcd1234.supabase.co/', SUPABASE_CLAVE_PUBLICA: 'publica'});
  assert.equal(r.status, 0);
  assert.match(readFileSync(destino, 'utf8'), /"supabaseUrl":"https:\/\/abcd1234\.supabase\.co","supabaseClave":"publica"/);
  restaurar();
});

test('se niega a publicar la clave de servicio o una URL que no es de Supabase', () => {
  assert.equal(correr({SUPABASE_URL: 'https://abcd1234.supabase.co', SUPABASE_CLAVE_PUBLICA: 'x', SUPABASE_CLAVE: 'x'}).status, 1);
  assert.equal(correr({SUPABASE_URL: 'https://otro.example.com', SUPABASE_CLAVE_PUBLICA: 'x'}).status, 1);
  restaurar();
});
