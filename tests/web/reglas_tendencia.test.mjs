// Pruebas de la tendencia de las cifras del tablero en línea (web/en_linea/reglas.js), sin navegador.
// Correr desde la raíz del repositorio:  node --test tests/web/*.test.mjs
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {abiertoEn, serieSemanas, textoTendencia} from '../../web/en_linea/reglas.js';

const DIA = 864e5;
const FIN = Date.parse('2026-11-12T12:00:00-05:00');            // jueves: la última ventana no es una semana de calendario
const iso = (t) => new Date(t).toISOString();
const hueco = (diasAtras, estado = 'detectado', cerradoDiasAtras = null) => ({
  primera_ts: iso(FIN - diasAtras * DIA), estado, ts_estado: cerradoDiasAtras == null ? null : iso(FIN - cerradoDiasAtras * DIA)});

test('abiertoEn: abierto desde la primera detección hasta que se cierra', () => {
  const h = hueco(20, 'reparado', 5);
  assert.equal(abiertoEn(h, FIN - 25 * DIA), false, 'antes de detectarse');
  assert.equal(abiertoEn(h, FIN - 10 * DIA), true, 'entre la detección y la reparación');
  assert.equal(abiertoEn(h, FIN), false, 'después de repararse');
  assert.equal(abiertoEn(hueco(3, 'verificado'), FIN), true, 'verificado sigue abierto');
  assert.equal(abiertoEn(hueco(9, 'descartado', 2), FIN - 4 * DIA), true, 'descartado: abierto hasta el descarte');
  assert.equal(abiertoEn({primera_ts: null, estado: 'detectado'}, FIN), false, 'sin fecha no cuenta');
});

test('serieSemanas abiertos: cuenta los abiertos al cierre de cada ventana de 7 días', () => {
  const huecos = [hueco(50), hueco(10), hueco(2), hueco(30, 'reparado', 12)];
  const s = serieSemanas(huecos, 'abiertos', FIN);
  assert.equal(s.length, 8);
  // cortes: FIN - 49, -42, -35, -28, -21, -14, -7 y 0 días. El reparado (detectado hace 30, reparado hace 12) cuenta
  // en -28, -21 y -14; el de hace 10 entra desde -7; el de hace 2, solo en el último corte.
  assert.deepEqual(s, [1, 1, 1, 2, 2, 2, 2, 3]);
});

test('serieSemanas reparados: cada reparación cae en una sola ventana (inicio excluido, fin incluido)', () => {
  const huecos = [hueco(40, 'reparado', 1), hueco(40, 'reparado', 7), hueco(40, 'reparado', 8), hueco(40, 'descartado', 3)];
  const s = serieSemanas(huecos, 'reparados', FIN);
  assert.deepEqual(s.slice(-2), [2, 1], 'el de hace 7 días exactos cuenta en la ventana anterior; el descartado no cuenta');
  assert.equal(s.reduce((a, b) => a + b, 0), 3);
});

test('serieSemanas: ventanas sin datos valen 0 y la serie no se acorta', () => {
  assert.deepEqual(serieSemanas([], 'abiertos', FIN), [0, 0, 0, 0, 0, 0, 0, 0]);
  assert.deepEqual(serieSemanas([], 'reparados', FIN, 4), [0, 0, 0, 0]);
});

test('textoTendencia: la frase dice el cambio en palabras', () => {
  assert.equal(textoTendencia([4, 5, 8], 'abiertos'), '3 más que 7 días antes');
  assert.equal(textoTendencia([9, 7], 'abiertos'), '2 menos que 7 días antes');
  assert.equal(textoTendencia([7, 7], 'abiertos'), 'igual que 7 días antes');
  assert.equal(textoTendencia([0, 2, 5], 'reparados'), '5 en 7 días · 2 en los 7 anteriores');
  assert.equal(textoTendencia([1200, 2500], 'abiertos'), '1.300 más que 7 días antes');
});
